from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


Planner_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = Planner_ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from Planner.step1_aas_input.context import collect_planning_context_from_kg


class _FakeAASClient:
    def __init__(self):
        self.shells = {
            "https://example/aas/productA": SimpleNamespace(
                id="https://example/aas/productA",
                id_short="productA",
                asset_information=SimpleNamespace(global_asset_id="asset-product", asset_type="Order"),
            ),
            "https://example/aas/resourceA": SimpleNamespace(
                id="https://example/aas/resourceA",
                id_short="resourceA",
                asset_information=SimpleNamespace(global_asset_id="asset-resource", asset_type="PlanarTable"),
            ),
            "https://example/aas/resourceB": SimpleNamespace(
                id="https://example/aas/resourceB",
                id_short="resourceB",
                asset_information=SimpleNamespace(global_asset_id="asset-resource-b", asset_type="DispensingSystem"),
            ),
        }
        self.submodels = {
            "https://example/aas/productA": [
                SimpleNamespace(id="sm-bop", id_short="BillOfProcesses", semantic_id=None),
                SimpleNamespace(id="sm-ai-product", id_short="AIPlanning", semantic_id=None),
            ],
            "https://example/aas/resourceA": [
                SimpleNamespace(id="sm-ai-resource", id_short="AIPlanning", semantic_id=None),
            ],
            "https://example/aas/resourceB": [
                SimpleNamespace(id="sm-ai-resource-b", id_short="AIPlanning", semantic_id=None),
            ],
        }
        self.submodel_raw = {
            "sm-bop": {
                "idShort": "BillOfProcesses",
                "submodelElements": [
                    {
                        "modelType": "SubmodelElementCollection",
                        "idShort": "Processes",
                        "value": [
                            {
                                "modelType": "SubmodelElementCollection",
                                "idShort": "Step1",
                                "value": [
                                    {
                                        "modelType": "ReferenceElement",
                                        "idShort": "RequiredCapability",
                                        "value": {
                                            "keys": [{"value": "https://example/cap/fill"}],
                                        },
                                    }
                                ],
                            }
                        ],
                    }
                ],
            },
            "sm-ai-product": {"idShort": "AIPlanning", "submodelElements": []},
            "sm-ai-resource": {"idShort": "AIPlanning", "submodelElements": []},
            "sm-ai-resource-b": {"idShort": "AIPlanning", "submodelElements": []},
        }

    def get_aas_by_id(self, aas_id):
        return self.shells.get(aas_id)

    def get_submodels_from_aas(self, aas_id):
        return self.submodels.get(aas_id, [])

    def get_submodel_raw(self, submodel_id):
        return self.submodel_raw.get(submodel_id)

    def find_submodel_by_semantic_id(self, aas_id, semantic_id):
        del aas_id, semantic_id
        return None

    def get_submodel_by_id(self, submodel_id):
        del submodel_id
        return None

    def lookup_aas_by_asset_id(self, global_asset_id):
        del global_asset_id
        return None


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class PlanningContextTests(unittest.TestCase):
    def test_collect_planning_context_from_kg_selects_capability_matched_assets(self):
        client = _FakeAASClient()
        # Under identity IRI strategy the AAS node IRI is the raw AAS id, returned as ?aas.
        sparql_payload = {
            "results": {
                "bindings": [
                    {
                        "aas": {"type": "uri", "value": "https://example/aas/resourceA"},
                        "providedCapability": {"value": "https://example/cap/move"},
                    },
                    {
                        "aas": {"type": "uri", "value": "https://example/aas/resourceB"},
                        "providedCapability": {"value": "https://example/cap/fill"},
                    },
                ]
            }
        }

        with patch(
            "Planner.step1_aas_input.context.requests.post",
            return_value=_FakeResponse(sparql_payload),
        ):
            context = collect_planning_context_from_kg(
                aas_client=client,
                order_aas_id="https://example/aas/productA",
                asset_ids=["https://example/aas/resourceA"],
                query_endpoint="http://kg-fuseki:3030/kg/sparql",
                abox_graph="urn:kg:abox",
                tbox_graph="urn:kg:tbox",
                timeout_seconds=3.0,
                enable_capability_matching=True,
            )

        self.assertIsNotNone(context)
        assert context is not None
        self.assertIn("https://example/aas/resourceB", context.resolved_asset_ids)

        source_ids = {source.aas_id for source in context.planning_sources}
        self.assertIn("https://example/aas/productA", source_ids)
        self.assertIn("https://example/aas/resourceA", source_ids)
        self.assertIn("https://example/aas/resourceB", source_ids)

    def test_collect_planning_context_from_kg_falls_back_when_query_fails(self):
        client = _FakeAASClient()

        with patch(
            "Planner.step1_aas_input.context.requests.post",
            side_effect=RuntimeError("Fuseki unavailable"),
        ):
            context = collect_planning_context_from_kg(
                aas_client=client,
                order_aas_id="https://example/aas/productA",
                asset_ids=["https://example/aas/resourceA"],
                query_endpoint="http://kg-fuseki:3030/kg/sparql",
                abox_graph="urn:kg:abox",
                tbox_graph="urn:kg:tbox",
                timeout_seconds=3.0,
                enable_capability_matching=True,
            )

        self.assertIsNotNone(context)
        assert context is not None
        self.assertIn("https://example/aas/resourceA", context.resolved_asset_ids)
        self.assertNotIn("https://example/aas/resourceB", context.resolved_asset_ids)


if __name__ == "__main__":
    unittest.main()
