"""
POST /api/validate

Accepts AAS JSON, converts to RDF, runs SHACL validation, returns structured issues.
Each issue includes a 'field' dot-path so the UI can route it to the right wizard step.
"""
from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# tools/ is not a package; add it to path for direct import
_TOOLS_DIR = _PROJECT_ROOT / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from run_resourceaas_validation import run_validation  # noqa: E402
from api.models import ValidateRequest, ValidateResponse, ValidationIssue  # noqa: E402

router = APIRouter()

_SHAPES = [
    _PROJECT_ROOT / "shacl" / "generated" / "shapes.generated.shacl.ttl",
    _PROJECT_ROOT / "shacl" / "manual" / "resourceaas-sparql-rules.shacl.ttl",
]
_ONTOLOGIES = [
    _PROJECT_ROOT / "ontology" / "CSS-Ontology.ttl",
    _PROJECT_ROOT / "ontology" / "CSSx.ttl",
]

_SEVERITY_MAP = {
    "http://www.w3.org/ns/shacl#Violation": "Violation",
    "http://www.w3.org/ns/shacl#Warning": "Warning",
    "http://www.w3.org/ns/shacl#Info": "Info",
}

# Maps SHACL result messages → dot-paths for UI step routing.
# Patterns tried in order; first match wins.
_MESSAGE_TO_FIELD: list[tuple[re.Pattern, str]] = [
    (re.compile(r"DigitalNameplate submodel is mandatory",          re.I), "DigitalNameplate"),
    (re.compile(r"HierarchicalStructures.*submodel is mandatory",   re.I), "HierarchicalStructures"),
    # Cross-submodel structural hints: field = the ABSENT submodel that must be added.
    (re.compile(r"AID submodel must be present",                    re.I), "AID"),
    (re.compile(r"SoftwareInterface must be present",               re.I), "AID"),
    (re.compile(r"ResourceInterface must be mapped",                re.I), "AID.InterfaceMQTT"),
    (re.compile(r"SkillInterface.*must use.*ResourceInterface",     re.I), "Skills"),
    (re.compile(r"exactly one SkillInterface",                      re.I), "Skills"),
    (re.compile(r"Skills submodel.*Capabilities submodel",          re.I), "Capabilities"),
    (re.compile(r"Capabilities submodel.*Skills submodel",          re.I), "Skills"),
    (re.compile(r"provides Skills.*must provide.*Capabilit",        re.I), "Capabilities"),
    (re.compile(r"provides Capabilit.*must provide.*Skill",         re.I), "Skills"),
    (re.compile(r"Capabilit.*isRealizedBySkill",                    re.I), "Capabilities"),
    (re.compile(r"serialNumber.*manufacturerName",                  re.I), "DigitalNameplate"),
    # BoM hints
    (re.compile(r"HierarchicalStructures.*Name is required",        re.I), "HierarchicalStructures.Name"),
    (re.compile(r"BoM entity.*globalAssetId",                       re.I), "HierarchicalStructures"),
    (re.compile(r"Archetype.*no entity entries",                    re.I), "HierarchicalStructures"),
    (re.compile(r"sourceSemanticId.*capabilit",                     re.I), "Capabilities"),
    (re.compile(r"sourceSemanticId.*skill",                         re.I), "Skills"),
    (re.compile(r"yearOfConstruction",                              re.I), "DigitalNameplate.YearOfConstruction"),
    (re.compile(r"dateOfManufacture",                               re.I), "DigitalNameplate.DateOfManufacture"),
    (re.compile(r"serialNumber",                                    re.I), "DigitalNameplate.SerialNumber"),
    (re.compile(r"manufacturerName",                                re.I), "DigitalNameplate.ManufacturerName"),
]


def _map_message_to_field(message: str) -> str:
    for pattern, field in _MESSAGE_TO_FIELD:
        if pattern.search(message):
            return field
    return ""


def _parse_report_ttl(report_ttl_path: Path) -> list[ValidationIssue]:
    """Extract sh:result entries from a SHACL report TTL file."""
    try:
        from rdflib import Graph, Namespace, RDF

        SH = Namespace("http://www.w3.org/ns/shacl#")
        g = Graph().parse(str(report_ttl_path), format="turtle")

        issues: list[ValidationIssue] = []
        seen_messages: set[str] = set()

        for result in g.subjects(RDF.type, SH.ValidationResult):
            severity_uri = str(g.value(result, SH.resultSeverity) or "")
            severity = _SEVERITY_MAP.get(severity_uri, severity_uri.split("#")[-1] or "Violation")

            message_node = g.value(result, SH.resultMessage)
            message = str(message_node) if message_node else "No message"

            if message in seen_messages:
                continue
            seen_messages.add(message)

            focus_node = g.value(result, SH.focusNode)
            focus_str = str(focus_node) if focus_node else None

            path_node = g.value(result, SH.resultPath)
            path_str = str(path_node) if path_node else None

            issues.append(ValidationIssue(
                severity=severity,
                message=message,
                field=_map_message_to_field(message),
                focus_node=focus_str,
                result_path=path_str,
            ))

        return issues
    except Exception:
        return []


@router.post("/validate", response_model=ValidateResponse)
async def validate_aas(req: ValidateRequest) -> ValidateResponse:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        json_path = tmp / "input.json"
        rdf_path = tmp / "generated.ttl"
        report_path = tmp / "report.ttl"

        json_path.write_text(req.json_text, encoding="utf-8")

        try:
            conforms, report_text = run_validation(
                input_json=json_path,
                generated_rdf=rdf_path,
                report_ttl=report_path,
                shapes_paths=_SHAPES,
                ontology_paths=_ONTOLOGIES,
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Validation error: {exc}")

        issues = _parse_report_ttl(report_path)
        report_ttl_text = report_path.read_text(encoding="utf-8") if report_path.exists() else report_text

    return ValidateResponse(conforms=conforms, issues=issues, report_ttl=report_ttl_text)
