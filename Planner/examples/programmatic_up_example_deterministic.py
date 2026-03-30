#!/usr/bin/env python3
"""Example: build a deterministic problem with unified-planning and solve it.

This demonstrates the new planner facade on the deterministic UP path.
"""


import sys
from pathlib import Path


_Planner_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_Planner_ROOT))

from solve import solve
from unified_planning.shortcuts import (
    BoolType, InstantaneousAction, Not, Problem, UserType)

def build_problem():
    problem = Problem("robot_move")
    location_type = UserType("Location")
    robot_at = problem.add_fluent("robot_at", BoolType(), loc=location_type)
    connected = problem.add_fluent(
        "connected", BoolType(), src=location_type, dst=location_type)
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


def _print_policy_summary(result, max_rules: int = 3) -> None:
    print("Policy summary:")
    print(f"  Rules: {len(result.policy)}")
    print(f"  FSAPs: {len(result.fsaps)}")

    if not result.policy:
        return

    print("  Sample rules:")
    for rule in result.policy[:max_rules]:
        condition = ", ".join(sorted(rule.condition)
                              ) if rule.condition else "<true>"
        print(f"    IF {condition}")
        print(f"    THEN {rule.action}")

    remaining = len(result.policy) - max_rules
    if remaining > 0:
        print(f"    ... {remaining} more")


def main():
    backend = sys.argv[1] if len(sys.argv) > 1 else "pr2"
    problem = build_problem()
    result = solve(problem, backend=backend)

    print(f"Backend: {result.backend_name}")
    print(f"Status:  {result.status}")
    print(f"Solved:  {result.is_solved}")
    print()

    if not result.is_solved:
        print("No plan found.")
        return

    if result.is_plan:
        print("Plan:")
        for action_instance in result.plan.actions:
            print(f"  - {action_instance}")
        return

    _print_policy_summary(result)


if __name__ == "__main__":
    main()
