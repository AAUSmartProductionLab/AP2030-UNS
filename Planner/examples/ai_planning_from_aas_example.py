#!/usr/bin/env python3
"""Run AIPlanning pipeline from an exported AAS JSON fixture.

Usage:
    python ai_planning_from_aas_example.py [aas_json_path] [output_xml]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_Planner_ROOT = Path(__file__).resolve().parent.parent
if str(_Planner_ROOT) not in sys.path:
    sys.path.insert(0, str(_Planner_ROOT))

from ai_pipeline import AIPlanningSource, run_ai_planning_pipeline


def main() -> int:
    default_input = _Planner_ROOT.parent / "Registration_Service" / "Resource" / "imaLoadingSystem2AAS.json"
    input_path = Path(sys.argv[1]) if len(sys.argv) > 1 else default_input
    output_path = Path(sys.argv[2]) if len(sys.argv) > 2 else _Planner_ROOT / "output" / "ai_planning_pipeline_bt.xml"

    if not input_path.exists():
        print(f"Input file not found: {input_path}")
        return 1

    with input_path.open("r") as handle:
        payload = json.load(handle)

    ai_planning_submodel = None
    for submodel in payload.get("submodels", []):
        if submodel.get("idShort") == "AIPlanning":
            ai_planning_submodel = submodel
            break

    if ai_planning_submodel is None:
        print("No AIPlanning submodel found in input JSON.")
        return 1

    source = AIPlanningSource(
        aas_id="https://smartproductionlab.aau.dk/aas/fixture",
        aas_name="fixture",
        ai_planning_submodel=ai_planning_submodel,
    )

    result = run_ai_planning_pipeline([source], timeout=20)

    print(f"Solve mode:  {result.solve_result.mode}")
    print(f"Backend:     {result.solve_result.backend_name}")
    print(f"Solved:      {result.solve_result.is_solved}")
    print(f"BT XML size: {len(result.bt_xml)}")
    print(f"Warnings:    {len(result.warnings)}")

    if result.artifacts:
        print("Artifacts:")
        for key, path in result.artifacts.items():
            print(f"  {key}: {path}")

    if result.bt_xml:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(result.bt_xml)
        print(f"BT XML written to: {output_path}")
    else:
        print("No BT XML produced.")

    if result.warnings:
        print("\nWarnings:")
        for warning in result.warnings:
            print(f"- {warning}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
