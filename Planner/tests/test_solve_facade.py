from __future__ import annotations

import sys
import unittest
from pathlib import Path


Planner_ROOT = Path(__file__).resolve().parent.parent
if str(Planner_ROOT) not in sys.path:
    sys.path.insert(0, str(Planner_ROOT))

from pddl_planning.planner_core.solver import solve


def build_problem():
    from unified_planning.shortcuts import BoolType, InstantaneousAction, Not, Problem, UserType

    problem = Problem("robot_move")
    location_type = UserType("Location")
    robot_at = problem.add_fluent("robot_at", BoolType(), loc=location_type)
    connected = problem.add_fluent("connected", BoolType(), src=location_type, dst=location_type)

    move = InstantaneousAction("move", src=location_type, dst=location_type)
    src = move.parameter("src")
    dst = move.parameter("dst")
    move.add_precondition(robot_at(src))
    move.add_precondition(connected(src, dst))
    move.add_precondition(Not(robot_at(dst)))
    move.add_effect(robot_at(src), False)
    move.add_effect(robot_at(dst), True)
    problem.add_action(move)

    l1 = problem.add_object("l1", location_type)
    l2 = problem.add_object("l2", location_type)
    problem.set_initial_value(robot_at(l1), True)
    problem.set_initial_value(robot_at(l2), False)
    problem.set_initial_value(connected(l1, l2), True)
    problem.set_initial_value(connected(l2, l1), True)
    problem.add_goal(robot_at(l2))
    return problem


def build_nondeterministic_problem():
    from unified_planning.shortcuts import BoolType, InstantaneousAction, Not, Problem, UserType

    problem = Problem("repair_move")
    location_type = UserType("Location")

    robot_at = problem.add_fluent("robot_at", BoolType(), loc=location_type)
    connected = problem.add_fluent("connected", BoolType(), src=location_type, dst=location_type)
    operational = problem.add_fluent("operational", BoolType())

    move = InstantaneousAction("move", src=location_type, dst=location_type)
    src = move.parameter("src")
    dst = move.parameter("dst")
    move.add_precondition(robot_at(src))
    move.add_precondition(connected(src, dst))
    move.add_precondition(operational)
    move.add_precondition(Not(robot_at(dst)))
    move.add_effect(robot_at(src), False)
    move.add_effect(robot_at(dst), True)
    move.add_oneof_effect(
        [
            [],
            [(operational, False)],
        ],
        labels=("ok", "break"),
    )
    problem.add_action(move)

    repair = InstantaneousAction("repair")
    repair.add_precondition(Not(operational))
    repair.add_effect(operational, True)
    problem.add_action(repair)

    l1 = problem.add_object("l1", location_type)
    l2 = problem.add_object("l2", location_type)
    problem.set_initial_value(robot_at(l1), True)
    problem.set_initial_value(robot_at(l2), False)
    problem.set_initial_value(connected(l1, l2), True)
    problem.set_initial_value(connected(l2, l1), False)
    problem.set_initial_value(operational, True)
    problem.add_goal(robot_at(l2))
    problem.add_goal(operational)
    return problem


class SolveFacadeTests(unittest.TestCase):
    def test_up_backend_returns_plan_result(self):
        result = solve(build_problem(), backend="up")
        self.assertTrue(result.is_plan)
        self.assertTrue(result.is_solved)
        self.assertGreaterEqual(len(result.plan.actions), 1)

    def test_pr2_backend_returns_policy_result_for_up_problem(self):
        result = solve(build_problem(), backend="pr2")
        self.assertTrue(result.is_policy)
        self.assertTrue(result.is_solved)
        self.assertEqual(result.backend_name, "pr2")
        self.assertGreater(len(result.policy), 0)
        self.assertGreaterEqual(len(result.fsaps), 0)
        self.assertTrue(result.domain_pddl)
        self.assertTrue(result.problem_pddl)

    def test_pr2_backend_supports_native_oneof_outcomes(self):
        result = solve(build_nondeterministic_problem(), backend="pr2")
        self.assertTrue(result.is_policy)
        self.assertTrue(result.is_solved)
        self.assertTrue(result.is_strong_cyclic)
        self.assertGreaterEqual(len(result.policy), 2)
        self.assertIn("oneof", result.domain_pddl)

    def test_auto_backend_routes_nondeterministic_problem_to_pr2(self):
        result = solve(build_nondeterministic_problem(), backend="auto")
        self.assertTrue(result.is_policy)
        self.assertEqual(result.backend_name, "pr2")
        self.assertTrue(result.is_solved)


if __name__ == "__main__":
    unittest.main()