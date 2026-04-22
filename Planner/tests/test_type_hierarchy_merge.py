from __future__ import annotations

import sys
import unittest
from pathlib import Path


Planner_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = Planner_ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from Planner.aas_to_pddl_conversion.up_builder import build_type_map, infer_type_parent_map


class TypeHierarchyInferenceTests(unittest.TestCase):
    def test_does_not_promote_semantic_type_under_aas_type(self):
        merged = {
            "fluents": [
                {
                    "key": "Operational",
                    "param_types": ["Resource"],
                }
            ],
            "actions": [
                {
                    "key": "Action1",
                    "parameters": [{"name": "r", "type": "planarTableShuttle1AAS"}],
                    "preconditions": [
                        {
                            "kind": "atom",
                            "fluent": "Operational",
                            "params": [{"kind": "action_param", "index": 0}],
                        }
                    ],
                    "effects": [],
                }
            ],
            "objects": [],
            "init_terms": [],
            "goal_terms": [],
            "constraints_terms": [],
        }

        warnings = []
        parent_map = infer_type_parent_map(merged, warnings)

        # Specific AAS type should inherit semantic class, not the other way around.
        self.assertEqual(parent_map.get("planarTableShuttle1AAS"), "Resource")
        self.assertNotEqual(parent_map.get("Resource"), "planarTableShuttle1AAS")

    def test_build_type_map_uses_thing_root_and_aliases_entity(self):
        def fake_user_type(name, father=None):
            return {"name": name, "father": father}

        warnings = []
        type_map = build_type_map(
            ["Entity", "owl:Thing", "Product", "MIM8AAS"],
            {
                "Product": "Entity",
                "MIM8AAS": "Product",
            },
            fake_user_type,
            warnings,
        )

        self.assertIn("Thing", type_map)
        self.assertIs(type_map["Entity"], type_map["Thing"])
        self.assertIs(type_map["owl:Thing"], type_map["Thing"])
        self.assertEqual(type_map["Product"]["father"], type_map["Thing"])
        self.assertEqual(type_map["MIM8AAS"]["father"], type_map["Product"])


if __name__ == "__main__":
    unittest.main()
