"""
POST /api/validate

Accepts AAS JSON, runs SHACL validation, returns structured issues. Each issue
includes a `field` dot-path so the UI can route it to the right wizard step.

Dispatches by `validation.profile` in `generation/config.yaml`:
  - "v2" (default) → `generation.v2.validator_v2.run_shacl_v2`
  - "v1"           → legacy `tools.run_resourceaas_validation.run_validation`

The response shape (ValidateResponse) is identical for both, so the UI is
unchanged.
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

from api.models import ValidateRequest, ValidateResponse, ValidationIssue  # noqa: E402
from generation.config import load_validation_paths, load_config  # noqa: E402

router = APIRouter()

_SHAPES, _ONTOLOGIES = load_validation_paths()

# Resolve the validation profile lazily — load_config() reads the same
# config.yaml that drives the generation pipeline. If config is malformed we
# fall back to v2 so the endpoint is self-healing.
def _active_profile() -> str:
    try:
        return load_config().validation_profile
    except SystemExit:
        return "v2"
    except Exception:
        return "v2"


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
    (re.compile(r"HierarchicalStructures.*Name is required",        re.I), "HierarchicalStructures.Name"),
    (re.compile(r"BoM entity.*globalAssetId",                       re.I), "HierarchicalStructures"),
    (re.compile(r"Archetype.*no entity entries",                    re.I), "HierarchicalStructures"),
    (re.compile(r"sourceSemanticId.*capabilit",                     re.I), "Capabilities"),
    (re.compile(r"sourceSemanticId.*skill",                         re.I), "Skills"),
    (re.compile(r"yearOfConstruction",                              re.I), "DigitalNameplate.YearOfConstruction"),
    (re.compile(r"dateOfManufacture",                               re.I), "DigitalNameplate.DateOfManufacture"),
    (re.compile(r"serialNumber",                                    re.I), "DigitalNameplate.SerialNumber"),
    (re.compile(r"manufacturerName",                                re.I), "DigitalNameplate.ManufacturerName"),
    # v2-specific common metamodel violations from aas-shacl-schema.ttl
    (re.compile(r"ManufacturerName",                                re.I), "DigitalNameplate.ManufacturerName"),
    (re.compile(r"ContactInformation",                              re.I), "DigitalNameplate"),
    (re.compile(r"OrderCodeOfManufacturer",                         re.I), "DigitalNameplate"),
]


def _map_message_to_field(message: str) -> str:
    for pattern, field in _MESSAGE_TO_FIELD:
        if pattern.search(message):
            return field
    return ""


# ---------------------------------------------------------------------------
# v1 path — kept for `validation.profile: v1`
# ---------------------------------------------------------------------------

def _validate_v1(json_text: str) -> ValidateResponse:
    from tools.run_resourceaas_validation import run_validation
    from rdflib import Graph, Namespace, RDF

    SH = Namespace("http://www.w3.org/ns/shacl#")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        json_path = tmp / "input.json"
        rdf_path = tmp / "generated.ttl"
        report_path = tmp / "report.ttl"
        json_path.write_text(json_text, encoding="utf-8")

        try:
            conforms, report_text = run_validation(
                input_json=json_path,
                generated_rdf=rdf_path,
                report_ttl=report_path,
                shapes_paths=_SHAPES,
                ontology_paths=_ONTOLOGIES,
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"v1 validation error: {exc}")

        issues: list[ValidationIssue] = []
        try:
            g = Graph().parse(str(report_path), format="turtle")
            seen: set[str] = set()
            for result in g.subjects(RDF.type, SH.ValidationResult):
                severity_uri = str(g.value(result, SH.resultSeverity) or "")
                severity = _SEVERITY_MAP.get(severity_uri, severity_uri.split("#")[-1] or "Violation")
                message_node = g.value(result, SH.resultMessage)
                message = str(message_node) if message_node else "No message"
                if message in seen:
                    continue
                seen.add(message)
                focus = g.value(result, SH.focusNode)
                path = g.value(result, SH.resultPath)
                issues.append(ValidationIssue(
                    severity=severity,
                    message=message,
                    field=_map_message_to_field(message),
                    focus_node=str(focus) if focus else None,
                    result_path=str(path) if path else None,
                ))
        except Exception:
            pass

        report_ttl_text = report_path.read_text(encoding="utf-8") if report_path.exists() else report_text

    return ValidateResponse(conforms=conforms, issues=issues, report_ttl=report_ttl_text)


# ---------------------------------------------------------------------------
# v2 path — `validation.profile: v2` (default)
# ---------------------------------------------------------------------------

def _validate_v2(json_text: str) -> ValidateResponse:
    from generation.v2.validator_v2 import run_shacl_v2

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        try:
            conforms, all_issues, _meta, _onto = run_shacl_v2(json_text, tmp)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"v2 validation error: {exc}")

        issues: list[ValidationIssue] = []
        seen: set[str] = set()
        for issue in all_issues:
            message = issue.get("message", "No message")
            if message in seen:
                continue
            seen.add(message)
            issues.append(ValidationIssue(
                severity=issue.get("severity", "Violation"),
                message=message,
                field=_map_message_to_field(message),
                focus_node=issue.get("focus_node") or None,
                result_path=None,
            ))

        report_path = tmp / "report.ttl"
        report_ttl_text = report_path.read_text(encoding="utf-8") if report_path.exists() else ""

    return ValidateResponse(conforms=conforms, issues=issues, report_ttl=report_ttl_text)


@router.post("/validate", response_model=ValidateResponse)
async def validate_aas(req: ValidateRequest) -> ValidateResponse:
    if _active_profile() == "v1":
        return _validate_v1(req.json_text)
    return _validate_v2(req.json_text)
