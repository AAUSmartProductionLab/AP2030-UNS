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
    def _product_parameter(self):
        return {"name": "product", "type": "Product"}

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
                    "parameters": [self._product_parameter()],
                    "preconditions": [],
                    "effects": [{"kind": "atom", "fluent": "station_ready", "params": [{"kind": "object", "name": "stationA"}]}],
                    "action_kind": "Action",
                    "sources": [("aas-1", "resourceA")],
                },
                {
                    "key": "RunStoppering",
                    "semantic_id": "http://www.w3id.org/aau-ra/cssx#StopperingSkill",
                    "skill_target": "http://www.w3id.org/aau-ra/cssx#StopperingSkill",
                    "parameters": [self._product_parameter()],
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
        step_ready = next(fluent for fluent in merged["fluents"] if fluent["key"] == "step_ready")
        step_done = next(fluent for fluent in merged["fluents"] if fluent["key"] == "step_done")
        self.assertEqual(step_ready.get("param_types"), ["Product", "Step"])
        self.assertEqual(step_done.get("param_types"), ["Product", "Step"])

        action_keys = [action["key"] for action in merged["actions"]]
        self.assertNotIn("RunDispensing", action_keys)
        self.assertNotIn("RunStoppering", action_keys)
        self.assertIn("MoveShuttle", action_keys)

        step_scoped = [action for action in merged["actions"] if action["key"].startswith("RunDispensing__")]
        self.assertEqual(len(step_scoped), 1)

        dispensing_action = step_scoped[0]
        self.assertTrue(any(term.get("kind") == "atom" and term.get("fluent") == "step_ready" for term in dispensing_action["preconditions"]))
        self.assertTrue(any(term.get("kind") == "atom" and term.get("fluent") == "step_done" for term in dispensing_action["effects"]))
        step_ready_precond = next(
            term
            for term in dispensing_action["preconditions"]
            if term.get("kind") == "atom" and term.get("fluent") == "step_ready"
        )
        self.assertEqual(step_ready_precond["params"][0].get("kind"), "action_param")
        self.assertEqual(step_ready_precond["params"][0].get("index"), 0)
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

    def test_compile_bop_ordering_initializes_step_state_per_product_instance(self):
        merged = {
            "fluents": [],
            "actions": [
                {
                    "key": "RunLoading",
                    "semantic_id": "http://www.w3id.org/aau-ra/cssx#LoadingSkill",
                    "semantic_ids": ["http://www.w3id.org/aau-ra/cssx#LoadingSkill"],
                    "skill_target": "Loading",
                    "parameters": [self._product_parameter()],
                    "preconditions": [],
                    "effects": [],
                    "action_kind": "Action",
                    "sources": [("aas-1", "loading")],
                }
            ],
            "objects": [
                {
                    "name": "mim8_0001",
                    "reference": "",
                    "declared_type": "mim8_0001aas",
                    "source_aas_id": "order",
                    "source_aas_name": "order",
                },
                {
                    "name": "mim8_0002",
                    "reference": "",
                    "declared_type": "mim8_0002aas",
                    "source_aas_id": "order",
                    "source_aas_name": "order",
                },
            ],
            "init_terms": [],
            "goal_terms": [
                {"kind": "atom", "fluent": "finished", "params": [{"kind": "object", "name": "mim8_0001"}]},
                {"kind": "atom", "fluent": "finished", "params": [{"kind": "object", "name": "mim8_0002"}]},
            ],
            "constraints_terms": [],
            "source_lookup": {},
        }
        bop_config = {
            "Processes": [
                {
                    "Loading": {
                        "step": 1,
                        "semantic_id": "http://www.w3id.org/aau-ra/cssx#LoadingCapability",
                    }
                },
            ]
        }

        compile_bop_ordering(merged, bop_config, [])

        step_ready_terms = [
            term
            for term in merged["init_terms"]
            if term.get("kind") == "atom" and term.get("fluent") == "step_ready"
        ]
        self.assertEqual(len(step_ready_terms), 2)
        ready_products = {term["params"][0].get("name") for term in step_ready_terms}
        self.assertEqual(ready_products, {"mim8_0001", "mim8_0002"})

        step_done_goals = [
            term
            for term in merged["goal_terms"]
            if term.get("kind") == "atom" and term.get("fluent") == "step_done"
        ]
        self.assertEqual(len(step_done_goals), 2)
        done_goal_products = {term["params"][0].get("name") for term in step_done_goals}
        self.assertEqual(done_goal_products, {"mim8_0001", "mim8_0002"})

    def test_compile_bop_ordering_matches_semantic_ids_only(self):
        merged = {
            "fluents": [],
            "actions": [
                {
                    "key": "Inspection",
                    "semantic_id": "http://www.w3id.org/aau-ra/cssx#DispensingSkill",
                    "semantic_ids": ["http://www.w3id.org/aau-ra/cssx#DispensingSkill"],
                    "skill_target": "Capture",
                    "parameters": [self._product_parameter()],
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
                    "parameters": [self._product_parameter()],
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

    def test_compile_bop_ordering_step_gates_station_occupy_actions(self):
        merged = {
            "fluents": [],
            "actions": [
                {
                    "key": "RunLoading",
                    "semantic_id": "http://www.w3id.org/aau-ra/cssx#LoadingCapability",
                    "semantic_ids": ["http://www.w3id.org/aau-ra/cssx#LoadingCapability"],
                    "skill_target": "Loading",
                    "parameters": [self._product_parameter()],
                    "preconditions": [],
                    "effects": [],
                    "action_kind": "Action",
                    "source_name": "imaLoadingSystemAAS",
                    "sources": [("loading", "imaLoadingSystemAAS")],
                },
                {
                    "key": "RunUnloading",
                    "semantic_id": "http://www.w3id.org/aau-ra/cssx#UnloadingCapability",
                    "semantic_ids": ["http://www.w3id.org/aau-ra/cssx#UnloadingCapability"],
                    "skill_target": "Unloading",
                    "parameters": [self._product_parameter()],
                    "preconditions": [],
                    "effects": [],
                    "action_kind": "Action",
                    "source_name": "optimaUnloadingSystemAAS",
                    "sources": [("unloading", "optimaUnloadingSystemAAS")],
                },
                {
                    "key": "OccupyLoading",
                    "semantic_id": "http://www.w3id.org/aau-ra/cssx#OccupyCapability",
                    "semantic_ids": ["http://www.w3id.org/aau-ra/cssx#OccupyCapability"],
                    "skill_target": "Occupy",
                    "parameters": [self._product_parameter()],
                    "preconditions": [],
                    "effects": [],
                    "action_kind": "Action",
                    "source_name": "imaLoadingSystemAAS",
                    "sources": [("loading", "imaLoadingSystemAAS")],
                },
                {
                    "key": "OccupyUnloading",
                    "semantic_id": "http://www.w3id.org/aau-ra/cssx#OccupyCapability",
                    "semantic_ids": ["http://www.w3id.org/aau-ra/cssx#OccupyCapability"],
                    "skill_target": "Occupy",
                    "parameters": [self._product_parameter()],
                    "preconditions": [],
                    "effects": [],
                    "action_kind": "Action",
                    "source_name": "optimaUnloadingSystemAAS",
                    "sources": [("unloading", "optimaUnloadingSystemAAS")],
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
                    "Loading": {
                        "step": 1,
                        "semantic_id": "http://www.w3id.org/aau-ra/cssx#LoadingCapability",
                    }
                },
                {
                    "Unloading": {
                        "step": 2,
                        "semantic_id": "http://www.w3id.org/aau-ra/cssx#UnloadingCapability",
                    }
                },
            ]
        }
        warnings = []

        compile_bop_ordering(merged, bop_config, warnings)

        action_keys = [action["key"] for action in merged["actions"]]
        self.assertNotIn("OccupyLoading", action_keys)
        self.assertNotIn("OccupyUnloading", action_keys)

        occupy_loading = [a for a in merged["actions"] if a["key"].startswith("OccupyLoading__")]
        occupy_unloading = [a for a in merged["actions"] if a["key"].startswith("OccupyUnloading__")]
        self.assertEqual(len(occupy_loading), 1)
        self.assertEqual(len(occupy_unloading), 1)

        loading_preconds = occupy_loading[0].get("preconditions", [])
        unloading_preconds = occupy_unloading[0].get("preconditions", [])

        self.assertTrue(any(term.get("kind") == "atom" and term.get("fluent") == "step_ready" for term in loading_preconds))
        self.assertTrue(any(term.get("kind") == "atom" and term.get("fluent") == "step_ready" for term in unloading_preconds))

    def _build_merged_with_action(self, action_effects):
        return {
            "fluents": [],
            "actions": [
                {
                    "key": "RunStep",
                    "semantic_id": "http://www.w3id.org/aau-ra/cssx#StepCapability",
                    "semantic_ids": ["http://www.w3id.org/aau-ra/cssx#StepCapability"],
                    "skill_target": "Step",
                    "parameters": [self._product_parameter()],
                    "preconditions": [],
                    "effects": action_effects,
                    "action_kind": "Action",
                    "sources": [("step", "stationAAS")],
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
            ],
            "init_terms": [],
            "goal_terms": [],
            "constraints_terms": [],
            "source_lookup": {},
        }

    def test_step_done_pushed_into_oneof_success_branch_only(self):
        """Loading-style action: only oneof at top level; failure branch is pure negation."""
        on_atom = {"kind": "atom", "fluent": "on", "params": []}
        productat_atom = {"kind": "atom", "fluent": "productat", "params": []}
        effects = [
            {
                "kind": "op",
                "op": "oneof",
                "children": [
                    {"kind": "op", "op": "and", "children": [on_atom, productat_atom]},
                    {"kind": "op", "op": "not", "children": [on_atom]},
                ],
            }
        ]
        merged = self._build_merged_with_action(effects)
        bop_config = {
            "Processes": [
                {"Step": {"step": 1, "semantic_id": "http://www.w3id.org/aau-ra/cssx#StepCapability"}},
            ]
        }
        compile_bop_ordering(merged, bop_config, [])

        scoped = next(a for a in merged["actions"] if a["key"].startswith("RunStep__"))
        top_level_effects = scoped["effects"]
        # step_done MUST NOT appear at top level — it must be inside the oneof's success branch.
        self.assertFalse(
            any(t.get("kind") == "atom" and t.get("fluent") == "step_done" for t in top_level_effects),
            "step_done leaked outside the oneof for an action with no deterministic positive effects",
        )

        oneof = next(t for t in top_level_effects if t.get("op") == "oneof")
        success, failure = oneof["children"]
        success_atoms = [c for c in success.get("children", []) if c.get("kind") == "atom"]
        self.assertTrue(any(a.get("fluent") == "step_done" for a in success_atoms))
        # Failure branch is pure negation and must remain so (no step_done injected).
        self.assertEqual(failure.get("op"), "not")

    def test_step_done_unconditional_when_deterministic_positive_present(self):
        """Capture-style action: oneof sits next to a deterministic positive effect."""
        captured_atom = {"kind": "atom", "fluent": "captured", "params": []}
        qok_atom = {"kind": "atom", "fluent": "qualityok", "params": []}
        effects = [
            captured_atom,
            {
                "kind": "op",
                "op": "oneof",
                "children": [
                    qok_atom,
                    {"kind": "op", "op": "not", "children": [qok_atom]},
                ],
            },
        ]
        merged = self._build_merged_with_action(effects)
        bop_config = {
            "Processes": [
                {"Step": {"step": 1, "semantic_id": "http://www.w3id.org/aau-ra/cssx#StepCapability"}},
            ]
        }
        compile_bop_ordering(merged, bop_config, [])

        scoped = next(a for a in merged["actions"] if a["key"].startswith("RunStep__"))
        top_level_effects = scoped["effects"]
        self.assertTrue(
            any(t.get("kind") == "atom" and t.get("fluent") == "step_done" for t in top_level_effects),
            "step_done should be unconditional when a deterministic positive effect exists alongside oneof",
        )
        # oneof children must remain unmodified (no step_done injected per branch).
        oneof = next(t for t in top_level_effects if t.get("op") == "oneof")
        for branch in oneof["children"]:
            self.assertNotEqual(branch.get("kind"), "op") if branch.get("kind") == "atom" else None
            if branch.get("kind") == "op" and branch.get("op") == "and":
                self.assertFalse(
                    any(c.get("fluent") == "step_done" for c in branch.get("children", []) if c.get("kind") == "atom")
                )


if __name__ == "__main__":
    unittest.main()
