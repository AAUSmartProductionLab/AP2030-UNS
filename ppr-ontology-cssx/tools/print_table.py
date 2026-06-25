"""print_table.py — print evaluation results as markdown tables.

Three views:
  1. Model comparison summary  — one row per equipment/model, key metrics side by side
  2. Per-attempt progression   — for every run, how violations and coverage changed
  3. Detail view (--detail)    — full metric dump per run

Column glossary (printed at the bottom of every table):
  Conforms   — Did the final AAS pass all SHACL shape constraints? (YES/NO)
  V@A1/2/3   — Number of SHACL violations on attempt 1 / 2 / 3 (— = not reached)
  Attempts   — Total retry-loop iterations consumed (1 = passed first try)
  MandCov    — Mandatory field coverage [0-1]: fraction of required SubmodelElements present
  ValAcc     — Value accuracy [0-1]: fraction of expected values found as substring in output
  Verify     — Uncertainty rate [0-1]: fraction of populated fields marked [VERIFY:] by the LLM
  Time(s)    — Wall-clock seconds for the full pipeline run (all attempts included)

Usage (from ppr-ontology-cssx/):
    python tools/print_table.py evaluation/results/<run_id>/results.jsonl
    python tools/print_table.py evaluation/results/<run_id>/results.jsonl --detail
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def _load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
    return rows


def _ratio(v) -> str:
    """Format a [0, 1] float as '0.850'. Returns 'n/a' for missing values."""
    if v is None:
        return "n/a"
    try:
        return f"{float(v):.3f}"
    except (TypeError, ValueError):
        return "n/a"


def _n(v) -> str:
    if v is None:
        return "n/a"
    try:
        return str(int(v))
    except (TypeError, ValueError):
        return "n/a"


def _yes_no(v) -> str:
    if v is True or v == 1:
        return "YES"
    if v is False or v == 0:
        return "NO"
    return "n/a"


def _model_short(model: str) -> str:
    """Shorten model names to fit table columns."""
    replacements = [
        ("claude-sonnet-4-6",        "sonnet-4.6"),
        ("claude-haiku-4-5-20251001", "haiku-4.5"),
        ("gemini-3.1-pro-preview",   "gem-3.1-pro"),
        ("gemini-3-flash-preview",   "gem-3-flash"),
        ("gemini-2.5-pro",           "gem-2.5-pro"),
        ("gemini-2.5-flash",         "gem-2.5-flash"),
    ]
    for full, short in replacements:
        if full in model:
            return short
    return model[:14]


def _violations_per_attempt(snaps: list[dict]) -> str:
    """Return 'A1:5N -> A2:0Y' style string from attempts_detail list."""
    if not snaps:
        return "n/a"
    parts = []
    for s in snaps:
        v = s.get("violations", "?")
        c = "Y" if s.get("conforms") else "N"
        parts.append(f"A{s['attempt']}:{v}{c}")
    return " -> ".join(parts)


# ----------------------------------------------------------------- view 1: model comparison


def print_model_comparison(rows: list[dict]) -> None:
    """One row per equipment/model — primary comparison view."""
    cols = [
        ("Model",      12),
        ("Equipment",  16),
        ("Conforms",    8),
        ("V@A1",        5),
        ("V@A2",        5),
        ("V@A3",        5),
        ("Attempts",    8),
        ("MandCov",     8),
        ("ValAcc",      7),
        ("Verify",      7),
        ("Time(s)",     7),
    ]
    sep    = "| " + " | ".join("-" * w for _, w in cols) + " |"
    header = "| " + " | ".join(name.ljust(w) for name, w in cols) + " |"

    print()
    print("## Model Comparison")
    print()
    print(header)
    print(sep)

    for row in rows:
        err   = row.get("error")
        m     = row.get("metrics") or {}
        snaps = row.get("attempts_detail") or []
        model = _model_short(row.get("model") or "?")
        equip = (row.get("equipment_id") or "?")[:16]

        v_a1 = _n(snaps[0]["violations"]) if len(snaps) > 0 else "n/a"
        v_a2 = _n(snaps[1]["violations"]) if len(snaps) > 1 else "-"
        v_a3 = _n(snaps[2]["violations"]) if len(snaps) > 2 else "-"

        if err:
            cells = [
                model.ljust(12), equip.ljust(16), "ERROR".ljust(8),
                "n/a".ljust(5), "n/a".ljust(5), "n/a".ljust(5), "n/a".ljust(8),
                "n/a".ljust(8), "n/a".ljust(7), "n/a".ljust(7), "n/a".ljust(7),
            ]
        else:
            cells = [
                model.ljust(12),
                equip.ljust(16),
                _yes_no(m.get("shacl_conforms")).ljust(8),
                v_a1.ljust(5),
                v_a2.ljust(5),
                v_a3.ljust(5),
                _n(m.get("attempts")).ljust(8),
                _ratio(m.get("mandatory_sme_coverage")).ljust(8),
                _ratio(m.get("value_substring_match")).ljust(7),
                _ratio(m.get("verify_rate")).ljust(7),
                f"{m.get('wallclock_seconds', 0):.1f}".ljust(7),
            ]
        print("| " + " | ".join(cells) + " |")

    print()
    _print_glossary()


def _print_glossary() -> None:
    print("**Column definitions:**")
    print("- **Conforms** -- Final AAS passed all SHACL shape constraints (YES/NO)")
    print("- **V@A1/A2/A3** -- SHACL violation count on attempt 1/2/3 ('-' = attempt not reached)")
    print("- **Attempts** -- Retry-loop iterations used (1 = zero-shot pass)")
    print("- **MandCov** -- Mandatory field coverage [0-1]: fraction of required SubmodelElements present")
    print("- **ValAcc** -- Value accuracy [0-1]: fraction of expected values matched by substring in output")
    print("- **Verify** -- Uncertainty rate [0-1]: fraction of populated fields flagged [VERIFY:] by the LLM")
    print("- **Time(s)** -- Wall-clock seconds for all pipeline attempts combined")
    print()


# ----------------------------------------------------------------- view 2: per-attempt progression


def print_attempt_progression(rows: list[dict]) -> None:
    """Per-run table showing how violations, coverage, and verify changed each attempt."""
    print()
    print("## Per-Attempt Progression (Validation Layer Impact)")
    print()

    for row in rows:
        snaps = row.get("attempts_detail") or []
        if not snaps:
            continue
        model = _model_short(row.get("model") or "?")
        equip = row.get("equipment_id") or "?"
        err   = row.get("error")

        print(f"### {model} -- {equip}")
        if err:
            print(f"  ERROR: {row.get('error_message', err[:80])}")
            print()
            continue

        has_coverage = any("mandatory_sme_coverage" in s for s in snaps)

        if has_coverage:
            cols = [("Attempt", 7), ("Conforms", 8), ("Violations", 10),
                    ("Metamodel", 9), ("Ontology", 8), ("Verify", 7),
                    ("MandCov", 8), ("ValAcc", 7)]
        else:
            cols = [("Attempt", 7), ("Conforms", 8), ("Violations", 10),
                    ("Metamodel", 9), ("Ontology", 8), ("Verify", 7)]

        header = "| " + " | ".join(n.ljust(w) for n, w in cols) + " |"
        sep    = "| " + " | ".join("-" * w for _, w in cols) + " |"
        print(header)
        print(sep)

        for s in snaps:
            verify_count = s.get("verify_count", 0)
            cells = [
                _n(s.get("attempt")).ljust(7),
                _yes_no(s.get("conforms")).ljust(8),
                _n(s.get("violations")).ljust(10),
                _n(s.get("metamodel")).ljust(9),
                _n(s.get("ontology")).ljust(8),
                _n(verify_count).ljust(7),
            ]
            if has_coverage:
                cells.append(_ratio(s.get("mandatory_sme_coverage")).ljust(8))
                cells.append(_ratio(s.get("value_substring_match")).ljust(7))
            print("| " + " | ".join(cells) + " |")
        print()


# ----------------------------------------------------------------- view 3: detail


def print_detail(rows: list[dict]) -> None:
    print()
    print("## Detailed Metrics Per Run")
    print()

    for row in rows:
        m     = row.get("metrics") or {}
        model = row.get("model") or "?"
        equip = row.get("equipment_id") or "?"
        err   = row.get("error")

        print(f"### {equip}  |  {model}")
        print()
        if err:
            print(f"  ERROR: {err[:120]}")
            print()
            continue

        entries = [
            ("SHACL conforms",          _yes_no(m.get("shacl_conforms"))),
            ("Violations (total)",       _n(m.get("shacl_violation_count"))),
            ("  - metamodel",            _n(m.get("shacl_metamodel_count"))),
            ("  - ontology",             _n(m.get("shacl_ontology_count"))),
            ("Attempts used",            _n(m.get("attempts"))),
            ("Mandatory field coverage", _ratio(m.get("mandatory_sme_coverage"))),
            ("Value accuracy",           _ratio(m.get("value_substring_match"))),
            ("Uncertainty rate",         _ratio(m.get("verify_rate"))),
            ("  [VERIFY:] count",        _n(m.get("verify_total"))),
            ("ArcheType valid",          _yes_no(m.get("archetype_value_in_enum"))),
            ("BoM globalAssetId",        _yes_no(m.get("bom_globalassetid_present"))),
            ("Wallclock (s)",            f"{m.get('wallclock_seconds', 0):.1f}"),
            ("Cost estimate (USD)",      f"{m.get('cost_estimate_usd', 0):.4f}"),
        ]
        w = max(len(label) for label, _ in entries)
        for label, val in entries:
            print(f"  {label.ljust(w)} : {val}")

        snaps = row.get("attempts_detail") or []
        if snaps:
            print(f"  {'Attempt progression'.ljust(w)} : {_violations_per_attempt(snaps)}")
        print()


# ----------------------------------------------------------------- main


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Print markdown metric tables from results.jsonl.")
    p.add_argument("results", type=Path, help="Path to results.jsonl.")
    p.add_argument("--detail", action="store_true", help="Also print full per-run detail table.")
    args = p.parse_args(argv)

    if not args.results.exists():
        print(f"ERROR: {args.results} not found.")
        return 1

    rows = _load_jsonl(args.results)
    if not rows:
        print(f"No rows in {args.results}")
        return 1

    valid_rows = [r for r in rows if not r.get("error") or r.get("metrics")]

    print(f"\n# Evaluation Results -- {args.results.parent.name}\n")
    print(f"Total runs: {len(rows)}  |  Valid: {len(valid_rows)}")

    print_model_comparison(valid_rows)
    print_attempt_progression(valid_rows)

    if args.detail:
        print_detail(valid_rows)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
