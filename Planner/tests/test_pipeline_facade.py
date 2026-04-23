from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


Planner_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = Planner_ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from Planner.aas_to_pddl_conversion.models import AIPlanningSource, _ParsedSource
from Planner.aas_to_pddl_conversion.pipeline import run_ai_planning_pipeline


class PipelineFacadeTests(unittest.TestCase):
    def test_run_ai_planning_pipeline_coordinates_stages_and_artifacts(self):
        source = AIPlanningSource(
            aas_id="https://example/aas/productA",
            aas_name="productA",
            ai_planning_submodel={"submodelElements": []},
        )
        parsed = _ParsedSource(aas_id=source.aas_id, aas_name=source.aas_name, warnings=["parse-warning"])
        merged = {"actions": [], "constraints_terms": []}
        semantic_problem = SimpleNamespace(
            _planner_metadata={
                "action_refs": {"act": {"source_aas_id": "aas://example/action"}},
                "predicate_refs": {},
            }
        )
        reduced_problem = SimpleNamespace(_planner_metadata={})
        solve_result = SimpleNamespace(
            is_plan=True,
            is_solved=True,
            metadata={"problem": semantic_problem},
        )
        capabilities = [SimpleNamespace(name="Dispensing", semantic_id="sid", resources={"res": "id"})]

        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch("Planner.aas_to_pddl_conversion.pipeline.parse_source", return_value=parsed), patch(
                "Planner.aas_to_pddl_conversion.pipeline.merge_sources", return_value=merged
            ), patch(
                "Planner.aas_to_pddl_conversion.pipeline.compile_bop_ordering"
            ) as compile_bop_mock, patch(
                "Planner.aas_to_pddl_conversion.pipeline.build_up_problem",
                side_effect=[semantic_problem, reduced_problem],
            ), patch(
                "Planner.aas_to_pddl_conversion.pipeline.solve_with_reduced_fallback", return_value=solve_result
            ) as solve_mock, patch(
                "Planner.aas_to_pddl_conversion.pipeline.build_capabilities", return_value=capabilities
            ), patch(
                "Planner.bt_synthesis.api.solve_result_to_bt_xml", return_value=("<root/>", ["bt-warning"])
            ), patch(
                "Planner.bt_synthesis.api.extract_plan_text", return_value="move a b"
            ), patch(
                "Planner.aas_to_pddl_conversion.pipeline.export_problem_artifacts",
                return_value={"artifacts_dir": tmp_dir},
            ):
                result = run_ai_planning_pipeline(
                    [source],
                    planning_timeout_seconds=12.0,
                    strict_semantic_solve=True,
                    bop_config={"Processes": []},
                    artifacts_dir=tmp_dir,
                )

        self.assertEqual(result.bt_xml, "<root/>")
        self.assertIn("parse-warning", result.warnings)
        self.assertIn("bt-warning", result.warnings)
        self.assertEqual(result.capabilities, capabilities)
        self.assertIn("behavior_tree_xml", result.artifacts)
        self.assertIn("deterministic_plan", result.artifacts)
        self.assertTrue(result.artifacts["behavior_tree_xml"].endswith("behavior_tree.xml"))
        self.assertTrue(result.artifacts["deterministic_plan"].endswith("deterministic_plan.txt"))
        self.assertEqual(result.planner_metadata.get("action_refs", {}).get("act", {}).get("source_aas_id"), "aas://example/action")
        self.assertEqual(
            solve_result.metadata.get("planner_metadata", {}).get("action_refs", {}).get("act", {}).get("source_aas_id"),
            "aas://example/action",
        )

        solve_call = solve_mock.call_args.kwargs
        self.assertEqual(solve_call["timeout"], 12.0)
        self.assertFalse(solve_call["allow_reduced_fallback"])

        compile_call_args = compile_bop_mock.call_args.args
        self.assertEqual(compile_call_args[0], merged)
        self.assertEqual(compile_call_args[1], {"Processes": []})


if __name__ == "__main__":
    unittest.main()
