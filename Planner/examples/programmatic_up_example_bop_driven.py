#!/usr/bin/env python3
"""Unified-planning BOP-driven FOND example with PR2 policy visualization.

This is the UP-based counterpart to ``programmatic_fond_example_bop_driven``
example. Because the current direct UP->PR2 bridge does not lower axioms or existential
predecessor checks yet, the BOP ordering is compiled explicitly into step-specific actions
and ``step_ready`` fluents.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_Planner_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_Planner_ROOT))

from pddl_planning.planner_core.solver import solve
from pddl_planning.visualization import create_force_graph_html


HGH_BOP = [
    {"step": "dispensing", "capability": "dispensing"},
]

HGH_FULL_BOP = [
    {"step": "dispensing", "capability": "dispensing"},
    {"step": "stoppering", "capability": "stoppering"},
    {"step": "inspection", "capability": "quality_ctrl"},
]

RESOURCE_CATALOG = {
    "loading": [("loader1", "Loader")],
    "dispensing": [("dispenser1", "ProcessStation")],
    "stoppering": [("stopperer1", "ProcessStation")],
    "quality_ctrl": [("camera1", "ProcessStation")],
    "unloading": [("unloader1", "Unloader")],
}


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _select_bop(variant: str):
    normalized = variant.lower()
    if normalized in {"simple", "mini", "single"}:
        return HGH_BOP, "simple"
    if normalized in {"full", "default"}:
        return HGH_FULL_BOP, "full"
    raise ValueError(f"Unsupported BOP variant: {variant}")


def build_problem(bop, *, problem_suffix: str = "full"):
    try:
        from unified_planning.shortcuts import BoolType, InstantaneousAction, Not, Problem, UserType
    except ImportError as exc:
        raise RuntimeError(
            "This example requires unified-planning. Install it with 'pip install unified-planning'."
        ) from exc

    problem = Problem(f"aseptic_production_bop_up_{problem_suffix}")

    product_type = UserType("Product")
    resource_type = UserType("Resource")
    station_type = UserType("Station", father=resource_type)
    loader_type = UserType("Loader", father=station_type)
    unloader_type = UserType("Unloader", father=station_type)
    process_station_type = UserType("ProcessStation", father=station_type)
    shuttle_type = UserType("Shuttle", father=resource_type)
    step_type = UserType("Step")

    occupied = problem.add_fluent("occupied", BoolType(), resource=resource_type, product=product_type)
    operational = problem.add_fluent("operational", BoolType(), resource=resource_type)
    on = problem.add_fluent("on", BoolType(), shuttle=shuttle_type, product=product_type)
    at = problem.add_fluent("at", BoolType(), shuttle=shuttle_type, station=station_type)
    product_at = problem.add_fluent("product_at", BoolType(), product=product_type, station=station_type)
    step_ready = problem.add_fluent("step_ready", BoolType(), product=product_type, step=step_type)
    step_done = problem.add_fluent("step_done", BoolType(), product=product_type, step=step_type)
    finished = problem.add_fluent("finished", BoolType(), product=product_type)

    product = problem.add_object("p0", product_type)
    shuttle = problem.add_object("shuttle0", shuttle_type)
    parking = problem.add_object("parking0", station_type)

    type_lookup = {
        "Loader": loader_type,
        "Unloader": unloader_type,
        "ProcessStation": process_station_type,
    }
    resource_objects = {}
    for entries in RESOURCE_CATALOG.values():
        for resource_name, resource_kind in entries:
            if resource_name in resource_objects:
                continue
            resource_objects[resource_name] = problem.add_object(resource_name, type_lookup[resource_kind])

    step_objects = []
    for index, step_def in enumerate(bop, start=1):
        step_name = f"step_{index}_{_slug(step_def['step'])}"
        step_objects.append(problem.add_object(step_name, step_type))

    occupy_transport = InstantaneousAction("occupy_transport", shuttle=shuttle_type, product=product_type)
    occupy_transport_shuttle = occupy_transport.parameter("shuttle")
    occupy_transport_product = occupy_transport.parameter("product")
    occupy_transport.add_precondition(operational(occupy_transport_shuttle))
    occupy_transport.add_precondition(Not(occupied(occupy_transport_shuttle, occupy_transport_product)))
    occupy_transport.add_effect(occupied(occupy_transport_shuttle, occupy_transport_product), True)
    problem.add_action(occupy_transport)

    occupy_station = InstantaneousAction(
        "occupy_station",
        station=station_type,
        product=product_type,
        shuttle=shuttle_type,
    )
    occupy_station_station = occupy_station.parameter("station")
    occupy_station_product = occupy_station.parameter("product")
    occupy_station_shuttle = occupy_station.parameter("shuttle")
    occupy_station.add_precondition(operational(occupy_station_station))
    occupy_station.add_precondition(Not(occupied(occupy_station_station, occupy_station_product)))
    occupy_station.add_precondition(occupied(occupy_station_shuttle, occupy_station_product))
    occupy_station.add_effect(occupied(occupy_station_station, occupy_station_product), True)
    problem.add_action(occupy_station)

    move = InstantaneousAction(
        "move",
        shuttle=shuttle_type,
        source=station_type,
        target=station_type,
        product=product_type,
    )
    move_shuttle = move.parameter("shuttle")
    move_source = move.parameter("source")
    move_target = move.parameter("target")
    move_product = move.parameter("product")
    move.add_precondition(at(move_shuttle, move_source))
    move.add_precondition(occupied(move_shuttle, move_product))
    move.add_precondition(occupied(move_target, move_product))
    move.add_precondition(operational(move_shuttle))
    move.add_precondition(Not(at(move_shuttle, move_target)))
    move.add_effect(at(move_shuttle, move_source), False)
    move.add_effect(at(move_shuttle, move_target), True)
    move.add_effect(product_at(move_product, move_source), False, on(move_shuttle, move_product))
    move.add_effect(product_at(move_product, move_target), True, on(move_shuttle, move_product))
    problem.add_action(move)

    repair = InstantaneousAction("repair", resource=resource_type)
    repair_resource = repair.parameter("resource")
    repair.add_precondition(Not(operational(repair_resource)))
    repair.add_effect(operational(repair_resource), True)
    problem.add_action(repair)

    for loader_name, _ in RESOURCE_CATALOG["loading"]:
        loader = resource_objects[loader_name]
        load = InstantaneousAction(f"load_{loader_name}", product=product_type, shuttle=shuttle_type)
        load_product = load.parameter("product")
        load_shuttle = load.parameter("shuttle")
        load.add_precondition(at(load_shuttle, loader))
        load.add_precondition(product_at(load_product, loader))
        load.add_precondition(occupied(load_shuttle, load_product))
        load.add_precondition(occupied(loader, load_product))
        load.add_precondition(Not(on(load_shuttle, load_product)))
        load.add_precondition(operational(loader))
        load.add_precondition(operational(load_shuttle))
        load.add_oneof_effect(
            [
                [(on(load_shuttle, load_product), True)],
                [(operational(loader), False)],
                [(on(load_shuttle, load_product), True), (operational(loader), False)],
            ],
            labels=("loaded", "broken", "loaded_broken"),
        )
        problem.add_action(load)

    for step_index, step_def in enumerate(bop):
        step_name = step_def["step"]
        capability = step_def["capability"]
        step_object = step_objects[step_index]
        next_step = step_objects[step_index + 1] if step_index + 1 < len(step_objects) else None
        success_effects = [
            (step_done(product, step_object), True),
            (step_ready(product, step_object), False),
        ]
        if next_step is not None:
            success_effects.append((step_ready(product, next_step), True))

        for resource_name, _ in RESOURCE_CATALOG[capability]:
            station = resource_objects[resource_name]
            action_name = f"process_{resource_name}_{_slug(step_name)}"
            process = InstantaneousAction(action_name, product=product_type)
            process_product = process.parameter("product")
            process.add_precondition(step_ready(process_product, step_object))
            process.add_precondition(Not(step_done(process_product, step_object)))
            process.add_precondition(product_at(process_product, station))
            process.add_precondition(occupied(station, process_product))
            process.add_precondition(operational(station))
            process.add_oneof_effect(
                [
                    success_effects,
                    [(operational(station), False)],
                    [*success_effects, (operational(station), False)],
                ],
                labels=("done", "broken", "done_broken"),
            )
            problem.add_action(process)

    last_step = step_objects[-1]
    for unloader_name, _ in RESOURCE_CATALOG["unloading"]:
        unloader = resource_objects[unloader_name]
        unload = InstantaneousAction(f"unload_{unloader_name}", product=product_type, shuttle=shuttle_type)
        unload_product = unload.parameter("product")
        unload_shuttle = unload.parameter("shuttle")
        unload.add_precondition(on(unload_shuttle, unload_product))
        unload.add_precondition(at(unload_shuttle, unloader))
        unload.add_precondition(occupied(unloader, unload_product))
        unload.add_precondition(occupied(unload_shuttle, unload_product))
        unload.add_precondition(step_done(unload_product, last_step))
        unload.add_precondition(operational(unloader))
        unload.add_precondition(operational(unload_shuttle))
        unload.add_oneof_effect(
            [
                [(on(unload_shuttle, unload_product), False), (finished(unload_product), True)],
                [(operational(unloader), False)],
                [
                    (on(unload_shuttle, unload_product), False),
                    (finished(unload_product), True),
                    (operational(unloader), False),
                ],
            ],
            labels=("finished", "broken", "finished_broken"),
        )
        problem.add_action(unload)

    for resource in [shuttle, *resource_objects.values()]:
        problem.set_initial_value(operational(resource), True)

    problem.set_initial_value(at(shuttle, parking), True)
    problem.set_initial_value(on(shuttle, product), False)
    problem.set_initial_value(occupied(shuttle, product), False)
    problem.set_initial_value(product_at(product, resource_objects["loader1"]), True)
    problem.set_initial_value(finished(product), False)

    for station in [parking, *resource_objects.values()]:
        problem.set_initial_value(at(shuttle, station), station == parking)
        problem.set_initial_value(product_at(product, station), station == resource_objects["loader1"])

    for resource in [shuttle, *resource_objects.values()]:
        problem.set_initial_value(occupied(resource, product), False)

    for index, step_object in enumerate(step_objects):
        problem.set_initial_value(step_ready(product, step_object), index == 0)
        problem.set_initial_value(step_done(product, step_object), False)

    problem.add_goal(finished(product))
    return problem


def write_policy_summary(result, output_dir: Path, problem_name: str) -> Path:
    rules_path = output_dir / f"{problem_name}_solver_rules.txt"
    lines = [
        f"Problem: {problem_name}",
        f"Backend: {result.backend_name}",
        f"Solved: {result.is_solved}",
        f"Strong Cyclic: {result.is_strong_cyclic}",
        f"Policy rules: {len(result.policy)}",
        f"FSAPs: {len(result.fsaps)}",
        "",
        "=== POLICY RULES ===",
    ]
    for index, rule in enumerate(result.policy, start=1):
        lines.append(f"[{index}] IF {set(rule.condition)}")
        lines.append(f"    THEN {rule.action}")
    lines.append("")
    lines.append("=== FSAPS ===")
    for index, fsap in enumerate(result.fsaps, start=1):
        lines.append(f"[{index}] IF {set(fsap.condition)}")
        lines.append(f"    FORBID {fsap.action}")
    rules_path.write_text("\n".join(lines) + "\n")
    return rules_path


def main():
    variant_arg = sys.argv[1] if len(sys.argv) > 1 else "full"
    bop, variant_name = _select_bop(variant_arg)
    problem = build_problem(bop, problem_suffix=variant_name)

    print("Problem:", problem.name)
    print(f"BOP steps: {[entry['step'] for entry in bop]}")
    print("Backend: pr2")
    print()

    result = solve(problem, backend="pr2", timeout=120)

    print(f"Backend:       {result.backend_name}")
    print(f"Solved:        {result.is_solved}")
    print(f"Strong Cyclic: {result.is_strong_cyclic}")
    print(f"Policy rules:  {len(result.policy)}")
    print(f"FSAPs:         {len(result.fsaps)}")
    print()

    if not result.is_solved:
        print("Solver failed -- check stderr:")
        print(result.stderr[-500:] if result.stderr else "(empty)")
        return 1

    output_dir = _Planner_ROOT / "output"
    output_dir.mkdir(exist_ok=True)

    rules_path = write_policy_summary(result, output_dir, problem.name)
    print(f"Rules written to {rules_path}")

    for rule in result.policy:
        print(f"  IF {set(rule.condition)}")
        print(f"    THEN {rule.action}")
    print()

    graph_path = output_dir / f"{problem.name}_state_graph.html"
    create_force_graph_html(
        result.require_policy_result(),
        graph_path,
        domain_name="aseptic_production_bop_up",
        problem_name=problem.name,
    )
    print(f"Interactive state graph: {graph_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())