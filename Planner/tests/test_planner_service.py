from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


Planner_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = Planner_ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from Planner.production_planner_service import (
    PlanningResult,
    PlannerConfig,
    PlannerService,
)


class PlannerServiceTests(unittest.TestCase):
    def test_planning_result_response_uses_new_fields(self):
        result = PlanningResult(
            success=True,
            process_aas_id="https://example/aas/process1",
            order_aas_id="https://example/aas/product1",
            planner_mode="plan",
            planner_backend="up",
            solver_status="SOLVED_SATISFICING",
            planner_warnings=["warn-a"],
            planning_artifacts={"behavior_tree_xml": "/tmp/behavior_tree.xml"},
            capabilities=[
                {
                    "Name": "Dispensing",
                    "SemanticId": "https://example/Capability/Dispensing",
                    "Resources": {"imaDispensing": "https://example/aas/dispensing"},
                }
            ],
        )

        payload = result.to_response_dict()

        self.assertEqual(payload["State"], "SUCCESS")
        self.assertIn("PlanningSummary", payload)
        self.assertIn("PlanningWarnings", payload)
        self.assertIn("PlannedCapabilities", payload)
        self.assertIn("PlanningArtifacts", payload)
        self.assertNotIn("MatchingSummary", payload)
        self.assertNotIn("MatchedCapabilities", payload)
        self.assertNotIn("UnmatchedCapabilities", payload)

    def test_plan_and_register_fails_hard_when_unsolved_in_strict_mode(self):
        config = PlannerConfig(save_intermediate_files=False, strict_semantic_solve=True)
        service = PlannerService(aas_client=object(), mqtt_client=object(), config=config)

        planning_sources = [SimpleNamespace(aas_id="https://example/aas/productA", asset_type="Product")]
        service.context_collector = Mock(return_value=SimpleNamespace(
            order_config={
                "id": "https://example/aas/productA",
                "idShort": "productA",
                "BatchInformation": {},
                "BillOfProcesses": {"Processes": []},
                "Requirements": {},
            },
            requirements={},
            resolved_asset_ids=["https://example/aas/dispensing"],
            planning_sources=planning_sources,
            planar_table_id=None,
        ))

        unsolved = SimpleNamespace(
            is_solved=False,
            is_policy=False,
            is_plan=False,
            mode="plan",
            backend_name="up",
            status="UNSOLVED",
            metadata={},
        )

        with patch("Planner.production_planner_service.parse_source", return_value=SimpleNamespace(warnings=[])), patch(
            "Planner.production_planner_service.merge_sources", return_value={"actions": [], "constraints_terms": []}
        ), patch(
            "Planner.production_planner_service.compile_bop_ordering"
        ) as compile_bop_mock, patch(
            "Planner.production_planner_service.build_up_problem", return_value=SimpleNamespace(_planner_metadata={})
        ), patch(
            "Planner.production_planner_service.export_problem_artifacts",
            return_value={"artifacts_dir": "/tmp", "domain_pddl": "/tmp/domain.pddl"},
        ), patch(
            "Planner.production_planner_service.solve_with_reduced_fallback", return_value=unsolved
        ) as solve_mock, patch(
            "Planner.production_planner_service.build_capabilities", return_value=[]
        ), patch(
            "Planner.production_planner_service.write_stage_metrics", return_value=None
        ), patch(
            "Planner.production_planner_service.publish_stage_metrics"
        ):
            result = service.plan_and_register(
                asset_ids=["https://example/aas/dispensing"],
                order_aas_id="https://example/aas/productA",
            )

        self.assertFalse(result.success)
        self.assertIn("strict mode", result.error_message)
        self.assertEqual(result.solver_status, "UNSOLVED")
        self.assertEqual(result.planner_backend, "up")
        self.assertEqual(result.planner_mode, "plan")

        solve_call = solve_mock.call_args.kwargs
        self.assertEqual(solve_call["timeout"], config.planning_timeout_seconds)
        self.assertFalse(solve_call["allow_reduced_fallback"])

        compile_call_args = compile_bop_mock.call_args.args
        self.assertEqual(compile_call_args[1], {"Processes": []})

    def test_plan_and_register_success_uses_pipeline_capabilities_for_process_config(self):
        config = PlannerConfig(
            save_intermediate_files=False,
            strict_semantic_solve=False,
            planning_timeout_seconds=12.5,
            ai_artifacts_dir="/tmp/planner-artifacts",
        )
        service = PlannerService(aas_client=object(), mqtt_client=object(), config=config)

        order_config = {
            "id": "https://example/aas/productA",
            "idShort": "productA",
            "BatchInformation": {},
            "BillOfProcesses": {"Processes": []},
            "Requirements": {"x": 1},
        }
        planning_sources = [SimpleNamespace(aas_id="https://example/aas/productA", asset_type="Product")]
        service.context_collector = Mock(return_value=SimpleNamespace(
            order_config=order_config,
            requirements={"x": 1},
            resolved_asset_ids=["https://example/aas/dispensing"],
            planning_sources=planning_sources,
            planar_table_id="https://example/aas/planartable",
        ))

        service.process_generator = Mock()
        process_bundle = SimpleNamespace(
            process_aas_id="https://example/aas/processA",
            system_id="ProcessAAS",
            config={"proc": {"id": "https://example/aas/processA"}},
            yaml_content="proc:\n  id: https://example/aas/processA\n",
            output_path=None,
        )
        service.process_generator.generate_process_aas_bundle.return_value = process_bundle

        capabilities = [
            SimpleNamespace(
                name="Dispensing",
                semantic_id="https://example/Capability/Dispensing",
                resources={"imaDispensing": "https://example/aas/dispensing"},
            )
        ]
        policy_result = SimpleNamespace(policy=["if ... then ..."])
        solved = SimpleNamespace(
            is_solved=True,
            is_policy=True,
            is_plan=False,
            mode="policy",
            backend_name="pr2-direct",
            status="SOLVED_POLICY",
            policy=["if ... then ..."],
            metadata={"problem": SimpleNamespace(_planner_metadata={})},
        )
        solved.require_policy_result = Mock(return_value=policy_result)

        with patch("Planner.production_planner_service.parse_source", return_value=SimpleNamespace(warnings=[])), patch(
            "Planner.production_planner_service.merge_sources", return_value={"actions": [], "constraints_terms": []}
        ), patch(
            "Planner.production_planner_service.compile_bop_ordering"
        ), patch(
            "Planner.production_planner_service.build_up_problem", return_value=SimpleNamespace(_planner_metadata={})
        ), patch(
            "Planner.production_planner_service.export_problem_artifacts", return_value={"artifacts_dir": "/tmp"}
        ), patch(
            "Planner.production_planner_service.solve_with_reduced_fallback", return_value=solved
        ), patch(
            "Planner.production_planner_service.build_trivial_bt", return_value=SimpleNamespace(root=object())
        ), patch(
            "Planner.production_planner_service.optimize_bt", return_value=SimpleNamespace(root=object())
        ), patch(
            "Planner.production_planner_service.bt_to_xml", return_value="<root BTCPP_format=\"4\" />"
        ), patch(
            "Planner.production_planner_service.count_bt_nodes", side_effect=[9, 12]
        ), patch(
            "Planner.production_planner_service.export_policy_visualization"
        ), patch(
            "Planner.production_planner_service.build_capabilities", return_value=capabilities
        ), patch(
            "Planner.production_planner_service.write_stage_metrics", return_value=None
        ), patch(
            "Planner.production_planner_service.publish_stage_metrics"
        ):
            result = service.plan_and_register(
                asset_ids=["https://example/aas/dispensing"],
                order_aas_id="https://example/aas/productA",
            )

        self.assertTrue(result.success)
        self.assertEqual(result.process_aas_id, "https://example/aas/processA")
        self.assertEqual(result.planner_mode, "policy")
        self.assertEqual(result.planner_backend, "pr2-direct")
        self.assertEqual(result.solver_status, "SOLVED_POLICY")
        self.assertEqual(result.capabilities[0]["Name"], "Dispensing")

        generate_args = service.process_generator.generate_process_aas_bundle.call_args.args
        self.assertEqual(generate_args[0], capabilities)
        self.assertEqual(generate_args[1], "https://example/aas/productA")
        self.assertEqual(generate_args[2], order_config)
        self.assertEqual(generate_args[3], "production_productA.xml")
        self.assertEqual(generate_args[4], "https://example/aas/planartable")
        self.assertIsNone(service.process_generator.generate_process_aas_bundle.call_args.kwargs["output_dir"])

        service.process_generator.publish_bundle_registration.assert_called_once_with(
            service.mqtt_client,
            service.config.registration_topic,
            process_bundle,
        )


if __name__ == "__main__":
    unittest.main()
