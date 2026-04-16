from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


Planner_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = Planner_ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from Planner.aas_to_pddl_conversion.parsing import parse_term
from Planner.aas_to_pddl_conversion.up_builder import build_up_problem
from Planner.pddl_planning.planner_core.solve_pipeline import solve_with_reduced_fallback


class _FakePolicyPlan:
    def __init__(self):
        self.last_map_fn = None

    def replace_action_instances(self, map_fn):
        self.last_map_fn = map_fn
        return "mapped-policy"


class _FakeSemanticResult:
    def __init__(self):
        self.is_plan = False
        self.is_policy = True
        self.is_solved = True
        self._policy_plan = _FakePolicyPlan()
        self._up_result = type("UPResult", (), {"plan": self._policy_plan})()
        self.policy_plan = self._policy_plan

    def require_plan_result(self):
        return self._up_result

    def require_policy_result(self):
        return self.policy_plan


class FondPipelineSupportTests(unittest.TestCase):
    def test_parse_term_recognizes_oneof_operator(self):
        term = {
            "modelType": "SubmodelElementCollection",
            "supplementalSemanticIds": [
                {
                    "keys": [
                        {
                            "value": "http://www.w3id.org/aau-ra/cssx#OneOf",
                        }
                    ]
                }
            ],
            "value": [],
        }

        parsed = parse_term(term, "resource", [])

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["kind"], "op")
        self.assertEqual(parsed["op"], "oneof")

    def test_build_up_problem_translates_oneof_effects(self):
        merged = {
            "fluents": [
                {
                    "key": "Loaded",
                    "param_types": [],
                    "value_type": "bool",
                }
            ],
            "actions": [
                {
                    "key": "Loading",
                    "skill_target": "Loading",
                    "parameters": [],
                    "preconditions": [],
                    "effects": [
                        {
                            "kind": "op",
                            "op": "oneof",
                            "children": [
                                {
                                    "kind": "atom",
                                    "fluent": "Loaded",
                                    "params": [],
                                },
                                {
                                    "kind": "op",
                                    "op": "not",
                                    "children": [
                                        {
                                            "kind": "atom",
                                            "fluent": "Loaded",
                                            "params": [],
                                        }
                                    ],
                                },
                            ],
                        }
                    ],
                    "action_kind": "Action",
                }
            ],
            "objects": [],
            "init_terms": [],
            "goal_terms": [],
            "constraints_terms": [],
        }
        warnings = []

        problem = build_up_problem(merged, warnings)
        loading = problem.action("Loading")

        self.assertEqual(len(loading.oneof_effects), 1)
        self.assertEqual(len(loading.oneof_effects[0].outcomes), 2)
        self.assertFalse(any("Unsupported effect operator 'oneof' ignored." in w for w in warnings))

    def test_solve_pipeline_maps_policy_after_constraint_compilation(self):
        warnings = []
        semantic_result = _FakeSemanticResult()
        map_back = lambda ai: ai

        with patch(
            "Planner.pddl_planning.planner_core.solve_pipeline.compile_trajectory_constraints",
            return_value=("compiled-problem", map_back),
        ), patch(
            "Planner.pddl_planning.planner_core.solve_pipeline.solve_problem",
            return_value=semantic_result,
        ):
            problem = type("Problem", (), {"trajectory_constraints": ["dummy"]})()
            result = solve_with_reduced_fallback(
                problem,
                timeout=1.0,
                warnings=warnings,
                allow_reduced_fallback=False,
                build_reduced_problem=lambda: None,
            )

        self.assertIs(result, semantic_result)
        self.assertEqual(result.require_plan_result().plan, "mapped-policy")
        self.assertEqual(result.require_policy_result(), "mapped-policy")
        self.assertFalse(any("Could not map compiled policy back" in w for w in warnings))


if __name__ == "__main__":
    unittest.main()