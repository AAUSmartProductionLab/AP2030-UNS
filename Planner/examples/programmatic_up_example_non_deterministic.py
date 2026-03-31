#!/usr/bin/env python3
"""Example: build a small nondeterministic problem with UP and solve it with PR2.

This uses the vendored unified-planning fork's native oneof action support.
"""

import sys
from pathlib import Path

_Planner_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_Planner_ROOT))

from planner_core.solver import solve


def build_problem():
    try:
        from unified_planning.shortcuts import BoolType, InstantaneousAction, Not, Problem, UserType
    except ImportError as exc:
        raise RuntimeError(
            "This example requires unified-planning. Install it with 'pip install unified-planning'."
        ) from exc

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


def main():
    result = solve(build_problem(), backend="pr2")

    print(f"Backend: {result.backend_name}")
    print(f"Status:  {result.status}")
    print(f"Solved:  {result.is_solved}")
    print(f"Strong Cyclic: {result.is_strong_cyclic}")
    print(f"Policy rules:  {len(result.policy)}")
    print(f"FSAPs:         {len(result.fsaps)}")
    print()

    if not result.is_solved:
        print("No strong-cyclic policy found.")
        return

    for rule in result.policy:
        print(f"IF {sorted(rule.condition)}")
        print(f"THEN {rule.action}")
        print()


if __name__ == "__main__":
    main()