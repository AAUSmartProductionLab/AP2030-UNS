from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


Planner_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = Planner_ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from Planner.aas_to_pddl_conversion.planning_context import collect_planning_context


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
        }
        self.submodels = {
            "https://example/aas/productA": [
                SimpleNamespace(id="sm-bop", id_short="BillOfProcesses", semantic_id=None),
                SimpleNamespace(id="sm-ai-product", id_short="AIPlanning", semantic_id=None),
            ],
            "https://example/aas/resourceA": [
                SimpleNamespace(id="sm-ai-resource", id_short="AIPlanning", semantic_id=None),
            ],
        }
        self.submodel_raw = {
            "sm-bop": {"idShort": "BillOfProcesses", "submodelElements": []},
            "sm-ai-product": {"idShort": "AIPlanning", "submodelElements": []},
            "sm-ai-resource": {"idShort": "AIPlanning", "submodelElements": []},
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


class PlanningContextTests(unittest.TestCase):
    def test_collect_planning_context_builds_expected_result(self):
        client = _FakeAASClient()

        ctx = collect_planning_context(
            client,
            order_aas_id="https://example/aas/productA",
            asset_ids=["https://example/aas/resourceA"],
        )

        self.assertIsNotNone(ctx)
        self.assertEqual(ctx.order_config["id"], "https://example/aas/productA")
        self.assertEqual(ctx.resolved_asset_ids, ["https://example/aas/resourceA"])
        self.assertEqual(len(ctx.planning_sources), 2)
        self.assertEqual(ctx.planar_table_id, "https://example/aas/resourceA")


if __name__ == "__main__":
    unittest.main()
