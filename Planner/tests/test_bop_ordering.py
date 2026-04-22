from __future__ import annotations

import sys
import unittest
from pathlib import Path


Planner_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = Planner_ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from Planner.aas_to_pddl_conversion.bop_ordering import compile_bop_ordering
from Planner.aas_to_pddl_conversion.utils import match_capability


class BoPOrderingTests(unittest.TestCase):
    def test_match_capability_accepts_capability_skill_uri_variants(self):
        self.assertTrue(
            match_capability(
                "http://www.w3id.org/aau-ra/cssx#DispensingCapability",
                "http://www.w3id.org/aau-ra/cssx#DispensingSkill",
            )
        )
        self.assertTrue(
            match_capability(
                "http://www.w3id.org/aau-ra/cssx#QualityControlCapability",
                "quality-control",
            )
        )
        self.assertFalse(
            match_capability(
                "http://www.w3id.org/aau-ra/cssx#DispensingCapability",
                "http://www.w3id.org/aau-ra/cssx#StopperingSkill",
            )
        )

    def test_compile_bop_ordering_injects_step_predicates_and_clones_actions(self):
        merged = {
            "fluents": [
                {
                    "key": "station_ready",
                    "semantic_id": "",
                    "param_types": ["Entity"],
                    "transformation": None,
                    "value_type": "bool",
                    "source": "test",
                }
            ],
            "actions": [
                {
                    "key": "RunDispensing",
                    "semantic_id": "http://www.w3id.org/aau-ra/cssx#DispensingSkill",
                    "skill_target": "http://www.w3id.org/aau-ra/cssx#DispensingSkill",
                    "parameters": [],
                    "preconditions": [],
                    "effects": [{"kind": "atom", "fluent": "station_ready", "params": [{"kind": "object", "name": "stationA"}]}],
                    "action_kind": "Action",
                    "sources": [("aas-1", "resourceA")],
                },
                {
                    "key": "RunStoppering",
                    "semantic_id": "http://www.w3id.org/aau-ra/cssx#StopperingSkill",
                    "skill_target": "http://www.w3id.org/aau-ra/cssx#StopperingSkill",
                    "parameters": [],
                    "preconditions": [],
                    "effects": [],
                    "action_kind": "Action",
                    "sources": [("aas-2", "resourceB")],
                },
                {
                    "key": "MoveShuttle",
                    "semantic_id": "http://www.w3id.org/aau-ra/cssx#MoveToPositionSkill",
                    "skill_target": "http://www.w3id.org/aau-ra/cssx#MoveToPositionSkill",
                    "parameters": [],
                    "preconditions": [],
                    "effects": [],
                    "action_kind": "Action",
                    "sources": [("aas-3", "planar")],
                },
            ],
            "objects": [
                {
                    "name": "product_1",
                    "reference": "",
                    "declared_type": "Product",
                    "source_aas_id": "order",
                    "source_aas_name": "order",
                },
                {
                    "name": "stationA",
                    "reference": "",
                    "declared_type": "Station",
                    "source_aas_id": "station",
                    "source_aas_name": "station",
                },
            ],
            "init_terms": [],
            "goal_terms": [],
            "constraints_terms": [],
            "source_lookup": {},
        }
        bop_config = {
            "Processes": [
                {
                    "Dispensing": {
                        "step": 1,
                        "semantic_id": "http://www.w3id.org/aau-ra/cssx#DispensingCapability",
                    }
                },
                {
                    "Stoppering": {
                        "step": 2,
                        "semantic_id": "http://www.w3id.org/aau-ra/cssx#StopperingCapability",
                    }
                },
            ]
        }
        warnings = []

        compile_bop_ordering(merged, bop_config, warnings)

        fluent_keys = {fluent["key"] for fluent in merged["fluents"]}
        self.assertIn("step_ready", fluent_keys)
        self.assertIn("step_done", fluent_keys)

        action_keys = [action["key"] for action in merged["actions"]]
        self.assertNotIn("RunDispensing", action_keys)
        self.assertNotIn("RunStoppering", action_keys)
        self.assertIn("MoveShuttle", action_keys)

        step_scoped = [action for action in merged["actions"] if action["key"].startswith("RunDispensing__")]
        self.assertEqual(len(step_scoped), 1)

        dispensing_action = step_scoped[0]
        self.assertTrue(any(term.get("kind") == "atom" and term.get("fluent") == "step_ready" for term in dispensing_action["preconditions"]))
        self.assertTrue(any(term.get("kind") == "atom" and term.get("fluent") == "step_done" for term in dispensing_action["effects"]))
        self.assertTrue(
            any(
                term.get("kind") == "atom"
                and term.get("fluent") == "step_ready"
                and len(term.get("params", [])) == 2
                and term["params"][1].get("name", "").startswith("step_2_")
                for term in dispensing_action["effects"]
            )
        )

        self.assertTrue(any(term.get("kind") == "atom" and term.get("fluent") == "step_done" for term in merged["goal_terms"]))
        self.assertGreaterEqual(len(merged["init_terms"]), 4)

    def test_compile_bop_ordering_matches_semantic_ids_only(self):
        merged = {
            "fluents": [],
            "actions": [
                {
                    "key": "Inspection",
                    "semantic_id": "http://www.w3id.org/aau-ra/cssx#DispensingSkill",
                    "semantic_ids": ["http://www.w3id.org/aau-ra/cssx#DispensingSkill"],
                    "skill_target": "Capture",
                    "parameters": [],
                    "preconditions": [],
                    "effects": [],
                    "action_kind": "Action",
                    "sources": ["dummy"],
                },
                {
                    "key": "Anything",
                    "semantic_id": "http://www.w3id.org/aau-ra/cssx#QualityControlCapability",
                    "semantic_ids": ["http://www.w3id.org/aau-ra/cssx#QualityControlCapability"],
                    "skill_target": "Capture",
                    "parameters": [],
                    "preconditions": [],
                    "effects": [],
                    "action_kind": "Action",
                    "sources": ["dummy"],
                },
            ],
            "objects": [
                {
                    "name": "product_1",
                    "reference": "",
                    "declared_type": "Product",
                    "source_aas_id": "order",
                    "source_aas_name": "order",
                }
            ],
            "init_terms": [],
            "goal_terms": [],
            "constraints_terms": [],
            "source_lookup": {},
        }
        bop_config = {
            "Processes": [
                {
                    "Inspection": {
                        "step": 1,
                        "semantic_id": "http://www.w3id.org/aau-ra/cssx#QualityControl",
                    }
                }
            ]
        }
        warnings = []

        compile_bop_ordering(merged, bop_config, warnings)

        action_keys = [action["key"] for action in merged["actions"]]
        self.assertIn("Inspection", action_keys)
        self.assertTrue(any(key.startswith("Anything__") for key in action_keys))


if __name__ == "__main__":
    unittest.main()
