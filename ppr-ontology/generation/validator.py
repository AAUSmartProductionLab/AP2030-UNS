"""
SHACL validation wrapper.
Owns all shape/ontology path constants so they don't leak into other modules.
"""
from __future__ import annotations

from pathlib import Path

from .config import load_validation_paths
from tools.run_resourceaas_validation import run_validation_detailed

_SHAPES, _ONTOLOGIES = load_validation_paths()


def run_shacl(json_text: str, tmp_dir: Path) -> tuple[bool, list[dict], list[dict], list[dict]]:
    """
    Write json_text to tmp_dir, run SHACL validation, parse the report.
    Returns (conforms, all_issues, metamodel_issues, ontology_issues).
    all_issues is the concatenation of both groups.
    """
    json_path   = tmp_dir / "input.json"
    rdf_path    = tmp_dir / "generated.ttl"
    report_path = tmp_dir / "report.ttl"
    json_path.write_text(json_text, encoding="utf-8")

    try:
        details = run_validation_detailed(json_path, rdf_path, report_path, _SHAPES, _ONTOLOGIES)
    except Exception as e:
        issues = [{"source": "validation", "severity": "Violation", "message": f"Validation error: {e}"}]
        return False, issues, issues, []

    metamodel_issues = list(details.get("metamodel_issues", []))
    ontology_issues = list(details.get("ontology_issues", []))
    issues = [*metamodel_issues, *ontology_issues]

    return bool(details.get("conforms", False)), issues, metamodel_issues, ontology_issues
