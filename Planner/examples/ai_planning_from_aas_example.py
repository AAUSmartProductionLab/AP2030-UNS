#!/usr/bin/env python3
"""Run AIPlanning pipeline from an exported AAS JSON fixture.

Usage:
    python ai_planning_from_aas_example.py [aas_json_path] [output_xml]
    python ai_planning_from_aas_example.py --strict [aas_json_path] [output_xml]
    python ai_planning_from_aas_example.py --non-strict [aas_json_path] [output_xml]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_Planner_ROOT = Path(__file__).resolve().parent.parent
_REPO_ROOT = _Planner_ROOT.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from Planner.aas_to_pddl_conversion.models import AIPlanningSource
from Planner.production_planner_service import PlannerService


def parse_args() -> argparse.Namespace:
    default_input = _Planner_ROOT.parent / "Registration_Service" / "Resource" / "imaLoadingSystem2AAS.json"
    default_output = _Planner_ROOT / "output" / "ai_planning_pipeline_bt.xml"

    parser = argparse.ArgumentParser(description="Run AIPlanning pipeline from an exported AAS JSON fixture.")
    parser.add_argument("aas_json_path", nargs="?", default=default_input, help="Path to exported AAS JSON input.")
    parser.add_argument("output_xml", nargs="?", default=default_output, help="Path to write output BT XML.")

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--strict",
        dest="strict_semantic_solve",
        action="store_true",
        help="Require full semantic solve support; disable reduced-model fallback.",
    )
    mode_group.add_argument(
        "--non-strict",
        dest="strict_semantic_solve",
        action="store_false",
        help="Allow reduced-model fallback when full semantic solve is unsupported.",
    )
    parser.set_defaults(strict_semantic_solve=False)

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.aas_json_path)
    output_path = Path(args.output_xml)

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

    service = PlannerService(aas_client=None)
    service.config.planning_timeout_seconds = 20
    service.config.strict_semantic_solve = bool(args.strict_semantic_solve)
    result = service._run_planning_pipeline([source])

    print(f"Strict mode: {service.config.strict_semantic_solve}")
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
