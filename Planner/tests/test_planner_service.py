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

        planning_sources = [object()]
        service.context_collector = Mock(return_value=SimpleNamespace(
            product_config={
                "id": "https://example/aas/productA",
                "idShort": "productA",
                "BatchInformation": {},
                "Requirements": {},
            },
            requirements={},
            resolved_asset_ids=["https://example/aas/dispensing"],
            planning_sources=planning_sources,
            planar_table_id=None,
        ))

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

        with patch.object(service, "_run_planning_pipeline", return_value=pipeline_result) as run_pipeline:
            result = service.plan_and_register(
                asset_ids=["https://example/aas/dispensing"],
                product_aas_id="https://example/aas/productA",
            )

        self.assertFalse(result.success)
        self.assertIn("strict mode", result.error_message)
        self.assertEqual(result.solver_status, "UNSOLVED")
        self.assertEqual(result.planner_backend, "up")
        self.assertEqual(result.planner_mode, "plan")

        run_pipeline.assert_called_once_with(planning_sources)

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
        planning_sources = [object()]
        service.context_collector = Mock(return_value=SimpleNamespace(
            product_config=product_config,
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

        with patch.object(service, "_run_planning_pipeline", return_value=pipeline_result) as run_pipeline:
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

        generate_args = service.process_generator.generate_process_aas_bundle.call_args.args
        self.assertEqual(generate_args[0], capabilities)
        self.assertEqual(generate_args[1], "https://example/aas/productA")
        self.assertEqual(generate_args[2], product_config)
        self.assertEqual(generate_args[3], {"x": 1})
        self.assertEqual(generate_args[5], "https://example/aas/planartable")
        self.assertIsNone(service.process_generator.generate_process_aas_bundle.call_args.kwargs["output_dir"])

        service.process_generator.publish_bundle_registration.assert_called_once_with(
            service.mqtt_client,
            service.config.registration_topic,
            process_bundle,
        )

        run_pipeline.assert_called_once_with(planning_sources)


if __name__ == "__main__":
    unittest.main()
