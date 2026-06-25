"""Pure metric functions for the evaluation harness — no I/O, no globals.

Every function takes a generated AAS dict (post-builder) and/or a ground-truth
manifest dict, returns a dict of numeric/boolean metrics. The runner aggregates
these into a single JSONL row per experiment.

Metric dictionary keys (stable wire format consumed by `plot_results.py`):

    submodel_coverage          float [0, 1] — fraction of expected submodels present
    sme_coverage               float [0, 1] — fraction of expected SMEs present (by idShort path)
    semanticid_exact_match     float [0, 1] — fraction of present SMEs whose semanticId matches expected
    semanticid_idta_alignment  float [0, 1] — fraction of present SMEs whose semanticId is from a known IDTA prefix
    value_substring_match      float [0, 1] — fraction of present SMEs with `expected_value_contains` satisfied
    verify_rate                float [0, 1] — fraction of all generated SMEs whose value is a [VERIFY:] marker
    shacl_conforms             bool
    shacl_metamodel_count      int — AAS-spec SHACL violations
    shacl_ontology_count       int — CSSx domain SHACL violations
    attempts                   int — pipeline retry-loop attempts (1 = no retry)
    wallclock_seconds          float
"""
from __future__ import annotations

import re
from typing import Any, Iterable


_VERIFY_RE = re.compile(r"\[VERIFY[:\]]")
_KNOWN_IDTA_PREFIXES = (
    "https://admin-shell.io/zvei/",
    "https://admin-shell.io/idta/",
    "https://admin-shell.io/aas/",
    "https://smartproductionlab.aau.dk/CSSx/",
)


# --------------------------------------------------------------------- helpers


def _walk_smes(submodel: dict) -> Iterable[tuple[list[str], dict]]:
    """Yield (path, sme) for every SubmodelElement in `submodel`, recursively.

    `path` is a list of idShort strings from the submodel root down to the SME,
    used as a stable address for ground-truth comparison.
    """
    for elem in submodel.get("submodelElements", []) or []:
        yield from _walk_element(elem, [])


def _walk_element(element: dict, path_prefix: list[str]) -> Iterable[tuple[list[str], dict]]:
    if not isinstance(element, dict):
        return
    idshort = element.get("idShort")
    if not idshort:
        return
    new_path = [*path_prefix, str(idshort)]
    yield new_path, element

    model_type = element.get("modelType")
    if model_type in ("SubmodelElementCollection", "SubmodelElementList"):
        for child in element.get("value", []) or []:
            yield from _walk_element(child, new_path)
    elif model_type == "Entity":
        for child in element.get("statements", []) or []:
            yield from _walk_element(child, new_path)
    elif model_type == "AnnotatedRelationshipElement":
        for child in element.get("annotations", []) or []:
            yield from _walk_element(child, new_path)


def _first_semantic_id(node: dict) -> str | None:
    semantic = node.get("semanticId") if isinstance(node, dict) else None
    keys = semantic.get("keys", []) if isinstance(semantic, dict) else []
    for key in keys:
        value = key.get("value") if isinstance(key, dict) else None
        if value:
            return str(value)
    return None


def _extract_value_text(sme: dict) -> str:
    """Return a string representation of an SME value for substring checks."""
    model_type = sme.get("modelType")
    value = sme.get("value")
    if model_type == "MultiLanguageProperty" and isinstance(value, list):
        return " ".join(str(v.get("text", "")) for v in value if isinstance(v, dict))
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    return ""


def _index_smes_by_path(submodel: dict) -> dict[tuple[str, ...], dict]:
    """Map ('SME', 'sub', 'leaf') → SME dict for the whole submodel tree."""
    return {tuple(path): elem for path, elem in _walk_smes(submodel)}


def _index_submodels_by_idshort(aas_doc: dict) -> dict[str, dict]:
    return {
        str(sm.get("idShort")): sm
        for sm in aas_doc.get("submodels", []) or []
        if isinstance(sm, dict) and sm.get("idShort")
    }


# --------------------------------------------------------------------- metrics


def coverage_metrics(aas_doc: dict, ground_truth: dict) -> dict[str, Any]:
    """Compute coverage / semanticId / value-match metrics against a ground truth.

    Ground-truth shape:
        expected_submodels:
          DigitalNameplate:
            submodelElements:
              - idShort: ManufacturerName
                path: [ManufacturerName]                # optional; defaults to [idShort]
                semanticId: "https://admin-shell.io/.../ManufacturerName"
                expected_value_contains: "Carlo Gavazzi"  # optional
                required: true                          # default true
    """
    submodels_index = _index_submodels_by_idshort(aas_doc)
    expected_submodels = ground_truth.get("expected_submodels") or {}

    sm_total = len(expected_submodels)
    sm_present = sum(1 for name in expected_submodels if name in submodels_index)

    sme_total = 0
    sme_present = 0
    sid_exact_match = 0
    sid_aligned = 0
    sid_total_present = 0
    value_match = 0
    value_total_with_check = 0

    misses: list[dict] = []  # diagnostic — SMEs the LLM didn't produce

    for sm_name, sm_truth in expected_submodels.items():
        actual_sm = submodels_index.get(sm_name)
        actual_index = _index_smes_by_path(actual_sm) if isinstance(actual_sm, dict) else {}

        for expected in (sm_truth or {}).get("submodelElements", []) or []:
            if not isinstance(expected, dict):
                continue
            required = expected.get("required", True)
            if not required:
                continue
            idshort = expected.get("idShort")
            if not idshort:
                continue
            path = tuple(expected.get("path") or [idshort])
            expected_sid = expected.get("semanticId")
            expected_value = expected.get("expected_value_contains")

            sme_total += 1
            actual = actual_index.get(path)
            if actual is None:
                misses.append({"submodel": sm_name, "path": list(path), "reason": "missing"})
                continue
            sme_present += 1
            sid_total_present += 1

            actual_sid = _first_semantic_id(actual)
            if expected_sid:
                if actual_sid == expected_sid:
                    sid_exact_match += 1
            elif actual_sid:
                sid_exact_match += 1  # no expectation -> any sid is fine
            if actual_sid and any(actual_sid.startswith(p) for p in _KNOWN_IDTA_PREFIXES):
                sid_aligned += 1

            if expected_value:
                value_total_with_check += 1
                actual_value_text = _extract_value_text(actual)
                if expected_value.lower() in actual_value_text.lower():
                    value_match += 1

    return {
        "submodel_coverage":        sm_present / sm_total if sm_total else 1.0,
        "sme_coverage":             sme_present / sme_total if sme_total else 1.0,
        "semanticid_exact_match":   sid_exact_match / sid_total_present if sid_total_present else 1.0,
        "semanticid_idta_alignment": sid_aligned / sid_total_present if sid_total_present else 1.0,
        "value_substring_match":    value_match / value_total_with_check if value_total_with_check else 1.0,
        "expected_submodels":       sm_total,
        "expected_smes":            sme_total,
        "present_smes":             sme_present,
        "misses":                   misses,
    }


def verify_rate(aas_doc: dict) -> dict[str, Any]:
    """Fraction of generated SME values containing a [VERIFY:] marker."""
    total = 0
    flagged = 0
    flagged_details: list[dict] = []
    for sm in aas_doc.get("submodels", []) or []:
        sm_idshort = sm.get("idShort", "?") if isinstance(sm, dict) else "?"
        for path, elem in _walk_smes(sm if isinstance(sm, dict) else {}):
            value_text = _extract_value_text(elem)
            if not value_text:
                continue
            total += 1
            if _VERIFY_RE.search(value_text):
                flagged += 1
                flagged_details.append({
                    "submodel": sm_idshort,
                    "path": list(path),
                    "value": value_text[:160],
                })

    return {
        "verify_rate":     flagged / total if total else 0.0,
        "verify_total":    flagged,
        "value_total":     total,
        "verify_misses":   flagged_details,
    }


def conformance_metrics(conforms: bool, metamodel_issues: list, ontology_issues: list) -> dict[str, Any]:
    return {
        "shacl_conforms":         bool(conforms),
        "shacl_metamodel_count":  len(metamodel_issues),
        "shacl_ontology_count":   len(ontology_issues),
        "shacl_violation_count":  len(metamodel_issues) + len(ontology_issues),
    }


def all_metrics(
    aas_doc: dict,
    ground_truth: dict,
    conforms: bool,
    metamodel_issues: list,
    ontology_issues: list,
    attempts: int,
    wallclock_seconds: float,
) -> dict[str, Any]:
    """Compute every metric and return a single flat dict ready for JSONL."""
    out: dict[str, Any] = {}
    out.update(coverage_metrics(aas_doc, ground_truth))
    out.update(verify_rate(aas_doc))
    out.update(conformance_metrics(conforms, metamodel_issues, ontology_issues))
    out["attempts"] = int(attempts)
    out["wallclock_seconds"] = float(wallclock_seconds)
    return out
