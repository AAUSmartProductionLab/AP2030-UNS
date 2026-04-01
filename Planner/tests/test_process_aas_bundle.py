from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock


Planner_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = Planner_ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from Planner.process_aas_generation_publishing.core.process_aas_generator import ProcessAASGenerator


class ProcessAASBundleTests(unittest.TestCase):
    def test_generate_process_aas_bundle_with_file_output(self):
        generator = ProcessAASGenerator()
        capabilities = [
            SimpleNamespace(
                name="Dispensing",
                semantic_id="https://example/Capability/Dispensing",
                resources={"imaDispensing": "https://example/aas/dispensing"},
            )
        ]
        product_info = {"BatchInformation": {"ProductName": "TestProduct"}}

        with tempfile.TemporaryDirectory() as tmp_dir:
            bundle = generator.generate_process_aas_bundle(
                planning_capabilities=capabilities,
                product_aas_id="https://example/aas/productA",
                product_info=product_info,
                requirements={},
                bt_filename="production_test.xml",
                planar_table_id="https://example/aas/planar",
                output_dir=tmp_dir,
            )

            self.assertTrue(bundle.process_aas_id.startswith("https://smartproductionlab.aau.dk/aas/Process_"))
            self.assertTrue(bundle.system_id.endswith("AAS"))
            self.assertIn(bundle.system_id, bundle.config)
            self.assertIn("Policy", bundle.config[bundle.system_id])
            self.assertIn("production_test.xml", bundle.yaml_content)
            self.assertIsNotNone(bundle.output_path)
            self.assertTrue(Path(bundle.output_path).exists())

    def test_generate_process_aas_bundle_without_file_output(self):
        generator = ProcessAASGenerator()
        capabilities = [
            SimpleNamespace(
                name="Loading",
                semantic_id="https://example/Capability/Loading",
                resources={"resourceA": "https://example/aas/resourceA"},
            )
        ]

        bundle = generator.generate_process_aas_bundle(
            planning_capabilities=capabilities,
            product_aas_id="https://example/aas/productB",
            product_info={"BatchInformation": {"ProductName": "NoFileProduct"}},
            requirements={},
            output_dir=None,
        )

        self.assertIsNone(bundle.output_path)
        self.assertIn("NoFileProduct", bundle.yaml_content)

    def test_build_registration_message_contains_expected_fields(self):
        generator = ProcessAASGenerator()

        message = generator.build_registration_message(
            asset_id="ProcessAAS",
            yaml_content="proc:\n  id: https://example/aas/processA\n",
        )

        self.assertIn("requestId", message)
        self.assertTrue(message["requestId"].startswith("planner-ProcessAAS-"))
        self.assertEqual(message["assetId"], "ProcessAAS")
        self.assertIn("proc:", message["configYaml"])

    def test_publish_registration_request_serializes_and_publishes(self):
        generator = ProcessAASGenerator()
        mqtt_client = Mock()

        published = generator.publish_registration_request(
            mqtt_client=mqtt_client,
            registration_topic="NN/Nybrovej/InnoLab/Registration/Config",
            asset_id="ProcessAAS",
            yaml_content="proc:\n  id: https://example/aas/processA\n",
        )

        mqtt_client.publish.assert_called_once()
        args, kwargs = mqtt_client.publish.call_args
        self.assertEqual(args[0], "NN/Nybrovej/InnoLab/Registration/Config")
        payload = json.loads(args[1])
        self.assertEqual(payload["assetId"], "ProcessAAS")
        self.assertIn("configYaml", payload)
        self.assertEqual(kwargs["qos"], 2)
        self.assertEqual(published["assetId"], "ProcessAAS")

    def test_publish_bundle_registration_uses_bundle_fields(self):
        generator = ProcessAASGenerator()
        mqtt_client = Mock()
        bundle = SimpleNamespace(
            system_id="ProcessAAS",
            yaml_content="proc:\n  id: https://example/aas/processA\n",
        )

        published = generator.publish_bundle_registration(
            mqtt_client=mqtt_client,
            registration_topic="NN/Nybrovej/InnoLab/Registration/Config",
            bundle=bundle,
        )

        payload = json.loads(mqtt_client.publish.call_args.args[1])
        self.assertEqual(payload["assetId"], "ProcessAAS")
        self.assertEqual(published["assetId"], "ProcessAAS")


if __name__ == "__main__":
    unittest.main()
