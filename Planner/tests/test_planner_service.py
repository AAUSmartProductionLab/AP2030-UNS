from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


Planner_ROOT = Path(__file__).resolve().parent.parent
if str(Planner_ROOT) not in sys.path:
    sys.path.insert(0, str(Planner_ROOT))

from aas_to_pddl.core.planner_service import PlanningResult, PlannerConfig, PlannerService


class _PipelineResult:
    def __init__(self, solve_result, bt_xml="", warnings=None, capabilities=None, artifacts=None):
        self.solve_result = solve_result
        self.bt_xml = bt_xml
        self.warnings = warnings or []
        self.capabilities = capabilities or []
        self.artifacts = artifacts or {}


class PlannerServiceTests(unittest.TestCase):
    def test_planning_result_response_uses_new_fields(self):
        result = PlanningResult(
            success=True,
            process_aas_id="https://example/aas/process1",
            product_aas_id="https://example/aas/product1",
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

        service._fetch_product_config = Mock(return_value={
            "id": "https://example/aas/productA",
            "idShort": "productA",
            "BatchInformation": {},
            "Requirements": {},
        })
        service._resolve_asset_hierarchies = Mock(return_value=["https://example/aas/dispensing"])
        service._collect_ai_planning_sources = Mock(return_value=[object()])

        unsolved = SimpleNamespace(
            is_solved=False,
            mode="plan",
            backend_name="up",
            status="UNSOLVED",
        )
        pipeline_result = _PipelineResult(
            solve_result=unsolved,
            warnings=["semantic unsolved"],
            artifacts={"domain_pddl": "/tmp/domain.pddl"},
        )

        with patch("ai_pipeline.run_ai_planning_pipeline", return_value=pipeline_result) as run_pipeline:
            result = service.plan_and_register(
                asset_ids=["https://example/aas/dispensing"],
                product_aas_id="https://example/aas/productA",
            )

        self.assertFalse(result.success)
        self.assertIn("strict mode", result.error_message)
        self.assertEqual(result.solver_status, "UNSOLVED")
        self.assertEqual(result.planner_backend, "up")
        self.assertEqual(result.planner_mode, "plan")

        kwargs = run_pipeline.call_args.kwargs
        self.assertFalse(kwargs["allow_reduced_fallback"])

    def test_plan_and_register_success_uses_pipeline_capabilities_for_process_config(self):
        config = PlannerConfig(
            save_intermediate_files=False,
            strict_semantic_solve=False,
            planning_timeout_seconds=12.5,
            ai_artifacts_dir="/tmp/planner-artifacts",
        )
        service = PlannerService(aas_client=object(), mqtt_client=object(), config=config)

        product_config = {
            "id": "https://example/aas/productA",
            "idShort": "productA",
            "BatchInformation": {},
            "Requirements": {"x": 1},
        }
        service._fetch_product_config = Mock(return_value=product_config)
        service._resolve_asset_hierarchies = Mock(return_value=["https://example/aas/dispensing"])
        service._collect_ai_planning_sources = Mock(return_value=[object()])
        service._find_planar_table_from_assets = Mock(return_value="https://example/aas/planartable")
        service._register_via_mqtt = Mock()

        service.process_generator = Mock()
        service.process_generator.generate_config.return_value = {"proc": {"id": "https://example/aas/processA"}}
        service.process_generator.get_aas_id.return_value = "https://example/aas/processA"
        service.process_generator.get_system_id.return_value = "ProcessAAS"

        capabilities = [
            SimpleNamespace(
                name="Dispensing",
                semantic_id="https://example/Capability/Dispensing",
                resources={"imaDispensing": "https://example/aas/dispensing"},
            )
        ]
        solved = SimpleNamespace(
            is_solved=True,
            mode="policy",
            backend_name="pr2-direct",
            status="SOLVED_POLICY",
        )
        pipeline_result = _PipelineResult(
            solve_result=solved,
            bt_xml="<root BTCPP_format=\"4\" />",
            warnings=["using policy conversion"],
            capabilities=capabilities,
            artifacts={"behavior_tree_xml": "/tmp/behavior_tree.xml"},
        )

        with patch("ai_pipeline.run_ai_planning_pipeline", return_value=pipeline_result) as run_pipeline:
            result = service.plan_and_register(
                asset_ids=["https://example/aas/dispensing"],
                product_aas_id="https://example/aas/productA",
            )

        self.assertTrue(result.success)
        self.assertEqual(result.process_aas_id, "https://example/aas/processA")
        self.assertEqual(result.planner_mode, "policy")
        self.assertEqual(result.planner_backend, "pr2-direct")
        self.assertEqual(result.solver_status, "SOLVED_POLICY")
        self.assertEqual(result.capabilities[0]["Name"], "Dispensing")

        generate_args = service.process_generator.generate_config.call_args.args
        self.assertEqual(generate_args[0], capabilities)
        self.assertEqual(generate_args[1], "https://example/aas/productA")
        self.assertEqual(generate_args[2], product_config)
        self.assertEqual(generate_args[3], {"x": 1})
        self.assertEqual(generate_args[5], "https://example/aas/planartable")

        kwargs = run_pipeline.call_args.kwargs
        self.assertTrue(kwargs["allow_reduced_fallback"])
        self.assertEqual(kwargs["timeout"], 12.5)
        self.assertEqual(kwargs["artifacts_dir"], "/tmp/planner-artifacts")


if __name__ == "__main__":
    unittest.main()
