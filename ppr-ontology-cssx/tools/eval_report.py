"""Standalone evaluation report for a generated AAS JSON.

Reads a generated AAS JSON and a ground-truth YAML, runs every metric from
evaluation/metrics.py, and prints a human-readable report. Optionally reads
the issues JSON written by the pipeline to identify what the validation loop
caught vs. what it let through.

Usage (from ppr-ontology-cssx/):
    python tools/eval_report.py \\
        --aas generation/output/aas_output.json \\
        --ground-truth evaluation/ground_truth/filling_module.yaml \\
        [--issues generation/output/aas_issues.json]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from evaluation import metrics as M  # noqa: E402


# ── helpers ──────────────────────────────────────────────────────────────────

def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _bar(value: float, width: int = 20) -> str:
    filled = round(value * width)
    return "[" + "#" * filled + "." * (width - filled) + f"] {value:.0%}"


def _sep(char: str = "-", width: int = 64) -> str:
    return char * width


def _pct(n: int, d: int) -> str:
    if d == 0:
        return "n/a"
    return f"{n}/{d} ({n/d:.0%})"


# ── "let through" analysis ────────────────────────────────────────────────────

_VERIFY_RE = re.compile(r"\[VERIFY[:\]]", re.IGNORECASE)


def _shacl_mentions(issues: list[dict], idshort: str) -> bool:
    """True if any SHACL issue message references this idShort."""
    pattern = re.compile(re.escape(idshort), re.IGNORECASE)
    for issue in issues:
        msg = issue.get("message", "") or ""
        if pattern.search(msg):
            return True
    return False


def _detailed_element_analysis(
    aas_doc: dict,
    ground_truth: dict,
    all_issues: list[dict],
) -> list[dict]:
    """
    For every element in ground_truth, determine:
      present      : bool
      value_ok     : bool | None  (None if no expected_value_contains)
      has_verify   : bool
      caught_by_shacl : bool  (SHACL violation references this idShort)
    Returns a flat list of dicts, one per expected element.
    """
    sm_index = M._index_submodels_by_idshort(aas_doc)
    rows: list[dict] = []

    for sm_name, sm_truth in (ground_truth.get("expected_submodels") or {}).items():
        actual_sm = sm_index.get(sm_name)
        actual_index = M._index_smes_by_path(actual_sm) if isinstance(actual_sm, dict) else {}

        for expected in (sm_truth or {}).get("submodelElements", []) or []:
            if not isinstance(expected, dict):
                continue
            idshort = expected.get("idShort")
            if not idshort:
                continue
            required = expected.get("required", True)
            path = tuple(expected.get("path") or [idshort])
            expected_value = expected.get("expected_value_contains")

            actual = actual_index.get(path)
            present = actual is not None
            value_ok: bool | None = None
            has_verify = False

            if present and actual is not None:
                text = M._extract_value_text(actual)
                has_verify = bool(_VERIFY_RE.search(text))
                if expected_value:
                    value_ok = expected_value.lower() in text.lower()

            rows.append({
                "submodel": sm_name,
                "path": "/".join(path),
                "idShort": idshort,
                "required": required,
                "present": present,
                "value_ok": value_ok,
                "has_verify": has_verify,
                "caught_by_shacl": _shacl_mentions(all_issues, idshort),
            })

    return rows


# ── report sections ───────────────────────────────────────────────────────────

def _print_conformance(issues_doc: dict | None, cov: dict) -> None:
    print()
    print(_sep("="))
    print("  SHACL CONFORMANCE")
    print(_sep())
    if issues_doc is None:
        print("  (no issues file provided -- conformance unknown)")
        return
    conforms = issues_doc.get("conforms", False)
    metamodel = issues_doc.get("metamodel") or []
    ontology = issues_doc.get("ontology") or []
    total = len(metamodel) + len(ontology)
    status = "CONFORMS" if conforms else "VIOLATIONS"
    print(f"  Result   : {status}")
    print(f"  Total violations: {total}  ({len(metamodel)} metamodel, {len(ontology)} ontology)")
    if metamodel:
        print()
        print("  Metamodel violations:")
        for v in metamodel[:5]:
            print(f"    [{v.get('severity','?')}] {str(v.get('message',''))[:100]}")
        if len(metamodel) > 5:
            print(f"    ... and {len(metamodel)-5} more")
    if ontology:
        print()
        print("  Ontology violations:")
        for v in ontology[:5]:
            print(f"    [{v.get('severity','?')}] {str(v.get('message',''))[:100]}")
        if len(ontology) > 5:
            print(f"    ... and {len(ontology)-5} more")


def _print_verify(vr: dict) -> None:
    print()
    print(_sep("="))
    print("  VERIFY MARKERS  (model uncertainty flags)")
    print(_sep())
    total = vr["value_total"]
    flagged = vr["verify_total"]
    rate = vr["verify_rate"]
    print(f"  Values checked  : {total}")
    print(f"  VERIFY-flagged  : {flagged}  {_bar(rate)}")
    if vr.get("verify_misses"):
        print()
        print("  Flagged items:")
        for item in vr["verify_misses"][:10]:
            sm = item.get("submodel", "?")
            path = "/".join(str(p) for p in item.get("path", []))
            val = item.get("value", "")[:80]
            print(f"    {sm}/{path}: {val}")
        if len(vr["verify_misses"]) > 10:
            print(f"    ... and {len(vr['verify_misses'])-10} more")


def _print_coverage(cov: dict) -> None:
    print()
    print(_sep("="))
    print("  COVERAGE vs GROUND TRUTH")
    print(_sep())
    print(f"  Submodel coverage    : {_bar(cov['submodel_coverage'])}")
    print(f"  Mandatory SME        : {_bar(cov['mandatory_sme_coverage'])}")
    print(f"  Optional SME         : {_bar(cov['optional_sme_coverage'])}")
    print(f"  SME F1 score         : {cov['sme_f1']:.3f}")
    print(f"  Value accuracy       : {_bar(cov['value_substring_match'])}")
    print(f"  SemanticId alignment : {_bar(cov['semanticid_idta_alignment'])}")
    print(f"  SemanticId exact     : {_bar(cov['semanticid_exact_match'])}")

    if cov.get("misses"):
        required_misses = [m for m in cov["misses"] if m.get("required")]
        optional_misses = [m for m in cov["misses"] if not m.get("required")]
        if required_misses:
            print()
            print("  Missing (required):")
            for m in required_misses:
                sm = m.get("submodel", "?")
                path = "/".join(str(p) for p in m.get("path", []))
                print(f"    X {sm}/{path}")
        if optional_misses:
            print()
            print("  Missing (optional):")
            for m in optional_misses[:8]:
                sm = m.get("submodel", "?")
                path = "/".join(str(p) for p in m.get("path", []))
                print(f"    - {sm}/{path}")
            if len(optional_misses) > 8:
                print(f"    ... and {len(optional_misses)-8} more")


def _print_let_through(rows: list[dict], all_issues: list[dict]) -> None:
    """Items that ground truth says are wrong/uncertain but SHACL didn't flag."""
    print()
    print(_sep("="))
    print("  LET THROUGH BY VALIDATION LOOP")
    print(_sep())
    print("  Items that ground truth identifies as incorrect/uncertain but SHACL did not flag.")
    print()

    let_through: list[dict] = []
    for r in rows:
        # Wrong value (either absent, value mismatch, or verify tag) AND not a SHACL violation
        issue = (
            not r["present"]
            or r["value_ok"] is False
            or r["has_verify"]
        )
        if issue and not r["caught_by_shacl"]:
            let_through.append(r)

    caught: list[dict] = [r for r in rows if r["caught_by_shacl"] and (not r["present"] or r["value_ok"] is False)]

    if not let_through and not caught:
        print("  (none -- all ground-truth checks passed or SHACL caught every problem)")
        return

    if let_through:
        print(f"  Let through ({len(let_through)} items):")
        for r in let_through:
            flag = ""
            if not r["present"]:
                flag = "MISSING"
            elif r["has_verify"]:
                flag = "VERIFY tag (model uncertain)"
            elif r["value_ok"] is False:
                flag = "value mismatch"
            req = "required" if r["required"] else "optional"
            print(f"    [{req}] {r['submodel']}/{r['path']}: {flag}")

    if caught:
        print()
        print(f"  Caught by SHACL ({len(caught)} items):")
        for r in caught[:5]:
            req = "required" if r["required"] else "optional"
            print(f"    [{req}] {r['submodel']}/{r['path']}")
        if len(caught) > 5:
            print(f"    ... and {len(caught)-5} more")


def _print_cross_refs(xr: dict) -> None:
    print()
    print(_sep("="))
    print("  CROSS-REFERENCE INTEGRITY")
    print(_sep())
    sl = xr["skill_links_to_aid_action"]
    cr = xr["capability_realizedby_skill"]
    st = xr["skill_total"]
    ct = xr["capability_total"]
    at = xr["aid_actions_count"]
    print(f"  Skills -> AID actions  : {_bar(sl)}  ({st} skills, {at} AID actions)")
    print(f"  Capabilities -> Skills : {_bar(cr)}  ({ct} capabilities)")
    print(f"  BOM globalAssetId      : {'OK' if xr['bom_globalassetid_present'] else 'MISSING (no SelfManagedEntity)'}")
    print(f"  ArcheType in enum      : {'OK' if xr['archetype_value_in_enum'] else 'FAIL (not Full/OneDown/OneUp)'}")


def _print_format(fv: dict) -> None:
    print()
    print(_sep("="))
    print("  FORMAT VIOLATIONS")
    print(_sep())
    print(f"  idShort violations : {fv['idshort_format_violations']}")
    print(f"  Value violations   : {fv['value_format_violations']}")
    if fv.get("value_format_details"):
        for detail in fv["value_format_details"][:5]:
            print(f"    {detail}")


# ── main ──────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Print an evaluation report for a generated AAS JSON.")
    p.add_argument("--aas", type=Path,
                   default=Path("generation/output/aas_output.json"),
                   help="Path to the generated AAS JSON (default: generation/output/aas_output.json)")
    p.add_argument("--ground-truth", type=Path, required=True,
                   help="Path to the ground-truth YAML (e.g. evaluation/ground_truth/filling_module.yaml)")
    p.add_argument("--issues", type=Path,
                   default=Path("generation/output/aas_issues.json"),
                   help="Path to the pipeline issues JSON (default: generation/output/aas_issues.json)")
    args = p.parse_args(argv)

    if not args.aas.exists():
        print(f"ERROR: AAS file not found: {args.aas}")
        return 1
    if not args.ground_truth.exists():
        print(f"ERROR: Ground truth file not found: {args.ground_truth}")
        return 1

    aas_doc = _load_json(args.aas)
    ground_truth = _load_yaml(args.ground_truth)

    # issues_doc normalised to {"conforms": bool, "metamodel": [...], "ontology": [...]}
    # or None if no file found.
    issues_doc: dict | None = None
    all_issues: list[dict] = []
    if args.issues.exists():
        raw = _load_json(args.issues)
        if isinstance(raw, list):
            # run_pipeline.py writes a plain list of violations
            all_issues = raw
            issues_doc = {"conforms": len(raw) == 0, "metamodel": raw, "ontology": []}
        elif isinstance(raw, dict):
            # run_eval.py writes {"conforms": bool, "metamodel": [...], "ontology": [...]}
            issues_doc = raw
            all_issues = (raw.get("metamodel") or []) + (raw.get("ontology") or [])

    # ── compute metrics ──
    cov = M.coverage_metrics(aas_doc, ground_truth)
    vr = M.verify_rate(aas_doc)
    fv = M.format_violations(aas_doc)
    xr = M.cross_reference_metrics(aas_doc)
    detail_rows = _detailed_element_analysis(aas_doc, ground_truth, all_issues)

    # ── print report ──
    asset = ground_truth.get("asset_name", args.aas.stem)
    sm_list = ", ".join(
        str(sm.get("idShort", "?"))
        for sm in aas_doc.get("submodels", [])
        if isinstance(sm, dict)
    )

    print()
    print(_sep("=", 64))
    print(f"  EVALUATION REPORT  --  {asset}")
    print(_sep("=", 64))
    print(f"  AAS file     : {args.aas}")
    print(f"  Ground truth : {args.ground_truth}")
    print(f"  Submodels    : {sm_list or '(none)'}")

    _print_conformance(issues_doc, cov)
    _print_verify(vr)
    _print_coverage(cov)
    _print_let_through(detail_rows, all_issues)
    _print_cross_refs(xr)
    _print_format(fv)

    # ── quick summary ──
    print()
    print(_sep("="))
    print("  SUMMARY")
    print(_sep())
    conforms_str = "CONFORMS" if (issues_doc or {}).get("conforms") else "UNKNOWN"
    print(f"  SHACL         : {conforms_str}  violations={len(all_issues)}")
    print(f"  Mand. coverage: {_bar(cov['mandatory_sme_coverage'])}")
    print(f"  Value accuracy: {_bar(cov['value_substring_match'])}")
    print(f"  Verify rate   : {_bar(vr['verify_rate'])}")
    print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
