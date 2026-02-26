#!/usr/bin/env python3
"""
Example: Programmatically define a FOND problem, solve with PR2, and
generate a BehaviorTree.CPP XML file.

Uses the ``pddl`` library to build the domain entirely in Python.

Requirements:
    pip install pddl>=0.2.0
"""

import sys
import os
from pathlib import Path

# Ensure pr2 root is on sys.path
_Planner_ROOT = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_PR2_ROOT = os.path.join(_Planner_ROOT, "pr2")
sys.path.insert(0, str(_PR2_ROOT))
sys.path.insert(0, str(_Planner_ROOT))


from pddl.logic import Predicate, constants, variables
from pddl.core import Domain, Problem
from pddl.action import Action
from pddl.logic.base import And, Not, OneOf
from pddl.requirements import Requirements

from pr2_adapter import PR2Solver
from pr2_to_bt import policy_to_bt, bt_to_xml
from visualize_policy_graph import create_force_graph_html

# Flag to enable/disable interactive visualization
VISUALIZE_POLICY = True


def build_domain():
    """Build the aseptic production domain.

    Station types: loader, dispenser, unloader, parking.
    Shuttle: carries products between stations.

    Process per product:
        occupy shuttle → occupy loader → move(parking→loader) → load →
        move(loader→dispenser) → dispense →
        move(dispenser→unloader) → unload →
        move(unloader→parking) → release stations → release shuttle
    """

    # ── Typed variables ───────────────────────────────────────────────
    [r]  = variables("r",  types=["resource"])
    [c]  = variables("c",  types=["resource"])   # shuttle
    [s]  = variables("s",  types=["resource"])   # station (for load/dispense/unload)
    [s1] = variables("s1", types=["resource"])   # move: from-station
    [s2] = variables("s2", types=["resource"])   # move: to-station
    [p]  = variables("p",  types=["product"])
    [t]  = variables("t",  types=["slot"])       # capacity slot token

    # ── Guard predicates (static — set once in init) ──────────────────
    is_shuttle   = Predicate("is_shuttle", r)
    is_loader    = Predicate("is_loader", r)
    is_dispenser = Predicate("is_dispenser", r)
    is_unloader  = Predicate("is_unloader", r)

    # ── State predicates ──────────────────────────────────────────────
    occupied    = Predicate("occupied", r, p)     # resource reserved for product
    operational = Predicate("operational", r)     # resources can only execute when operational
    free_slot   = Predicate("free_slot", r, t)   # capacity token t available on resource r
    on          = Predicate("on", c, p)           # product physically on shuttle
    at          = Predicate("at", c, s)           # shuttle docked at station
    dispensed   = Predicate("dispensed", p)
    finished    = Predicate("finished", p)

    predicates = [is_shuttle, is_loader, is_dispenser, is_unloader,
                  occupied, free_slot, on, at, dispensed, finished, operational]

    # ── Actions ───────────────────────────────────────────────────────

    # ── Occupy variants (typed, with production-ordering guards) ──────

    # Reserve shuttle for a product (first step — shuttle must have capacity)
    occupy_shuttle = Action(
        "occupy_shuttle", parameters=[c, p, t],
        precondition= operational(c) & is_shuttle(c) & free_slot(c, t),
        effect= occupied(c, p) & ~free_slot(c, t),
    )

    # Reserve loader — shuttle must already be reserved for this product
    occupy_loader = Action(
        "occupy_loader", parameters=[s, p, c, t],
        precondition=(operational(s) & is_loader(s)
                      & is_shuttle(c) & occupied(c, p) & free_slot(s, t)),
        effect= occupied(s, p) & ~free_slot(s, t),
    )

    # Reserve dispenser — product must already be loaded onto shuttle
    occupy_dispenser = Action(
        "occupy_dispenser", parameters=[s, p, c, t],
        precondition=( operational(s) & is_dispenser(s)
                      & is_shuttle(c) & on(c, p) & free_slot(s, t)),
        effect= occupied(s, p) & ~free_slot(s, t),
    )

    # Reserve unloader — product must already be dispensed
    occupy_unloader = Action(
        "occupy_unloader", parameters=[s, p, t],
        precondition=( operational(s) & is_unloader(s)
                      & dispensed(p) & free_slot(s, t)),
        effect= occupied(s, p) & ~free_slot(s, t),
    )

    # ── Release variants (typed, with completion guards) ──────────────

    # Release shuttle — only after product is finished
    release_shuttle = Action(
        "release_shuttle", parameters=[c, p, t],
        precondition=(occupied(c, p) & operational(c) & is_shuttle(c)
                      & finished(p) & ~free_slot(c, t)),
        effect= ~occupied(c, p) & free_slot(c, t),
    )

    # Release loader — only after product is loaded onto shuttle
    release_loader = Action(
        "release_loader", parameters=[s, p, c, t],
        precondition=(occupied(s, p) & operational(s) & is_loader(s)
                      & is_shuttle(c) & on(c, p) & ~free_slot(s, t)),
        effect= ~occupied(s, p) & free_slot(s, t),
    )

    # Release dispenser — only after product is dispensed
    release_dispenser = Action(
        "release_dispenser", parameters=[s, p, t],
        precondition=(occupied(s, p) & operational(s) & is_dispenser(s)
                      & dispensed(p) & ~free_slot(s, t)),
        effect= ~occupied(s, p) & free_slot(s, t),
    )

    # Release unloader — only after product is finished
    release_unloader = Action(
        "release_unloader", parameters=[s, p, t],
        precondition=(occupied(s, p) & operational(s) & is_unloader(s)
                      & finished(p) & ~free_slot(s, t)),
        effect= ~occupied(s, p) & free_slot(s, t),
    )

    # Move shuttle from one station to another
    # Destination must be occupied for the same product the shuttle carries.
    # Source station s1 must be where the shuttle currently is; at(c, s1) is
    # deleted so only one location is true at a time.
    moveToStation = Action(
        "move", parameters=[c, s1, s2, p],
        precondition=(is_shuttle(c) & at(c, s1) & occupied(c, p)
                      & occupied(s2, p) & operational(c)),
        effect=OneOf(
            ~at(c, s1) & at(c, s2),
            ~at(c, s1) & at(c, s2) & ~operational(c),
            ~at(c, s1) & ~operational(c),
            at(c, s1) & ~operational(c),
        ),
    )

    # Load product onto shuttle at a loading station
    load = Action(
        "load", parameters=[p, c, s],
        precondition=(is_shuttle(c) & is_loader(s)
                      & at(c, s) & occupied(c, p) & occupied(s, p)
                      & ~on(c, p) & operational(s) & operational(c)),
        effect=OneOf(
            on(c, p),
            ~operational(s),
            on(c, p) & ~operational(s),
        ),
    )

    repair = Action(
        "repair", 
        parameters=[r],
        precondition=(~operational(r)),
        effect=operational(r),
    )

    # Dispense product at a dispensing station
    dispense = Action(
        "dispense", parameters=[p, c, s],
        precondition=(is_shuttle(c) & is_dispenser(s)
                      & on(c, p) & at(c, s) & occupied(s, p) & operational(s) & operational(c)),
        effect=OneOf(
            dispensed(p),
            dispensed(p) & ~operational(s),
            ~operational(s),
        ),
    )

    # Unload product at an unloading station — product is finished
    unload = Action(
        "unload", parameters=[p, c, s],
        precondition=(is_shuttle(c) & is_unloader(s)
                      & on(c, p) & at(c, s) & occupied(s, p)
                      & dispensed(p) & operational(s) & operational(c)),
        effect=OneOf(
            ~on(c, p) & finished(p),
            ~on(c, p) & finished(p) & ~operational(s),
            ~operational(s),
        ),
    )

    actions = [occupy_shuttle, occupy_loader, occupy_dispenser, occupy_unloader,
               release_shuttle, release_loader, release_dispenser, release_unloader,
               moveToStation, load, dispense, unload, repair]

    # ── Domain ────────────────────────────────────────────────────────
    domain = Domain(
        "aseptic_production",
        requirements=[Requirements.STRIPS, Requirements.TYPING,
                      Requirements.NON_DETERMINISTIC],
        types={"resource": None, "product": None, "slot": None},
        predicates=predicates,
        actions=actions,
    )

    return domain, {
        "is_shuttle": is_shuttle, "is_loader": is_loader,
        "is_dispenser": is_dispenser, "is_unloader": is_unloader, "occupied": occupied, "on": on, "at": at,
        "dispensed": dispensed, "finished": finished, "operational": operational,
        "free_slot": free_slot,
    }


def build_problem(domain, preds, n_products=1, capacities=None):
    """Build a problem with *n_products*.

    *capacities*: dict mapping station kind → max concurrent products.
        Defaults: shuttle=1, loader=1, dispenser=1, unloader=1.
        Example:  {"shuttle": 1, "dispenser": 2}
    """
    default_caps = {"shuttle": 1, "loader": 1, "dispenser": 1, "unloader": 1}
    caps = {**default_caps, **(capacities or {})}

    products      = constants(" ".join(f"p{i}" for i in range(n_products)),
                              type_="product")
    shuttle_objs  = constants(" ".join(f"shuttle{i}" for i in range(1)), type_="resource")
    parking_objs  = constants("parking1 parking2", type_="resource")
    loader_objs   = constants("loader1", type_="resource")
    disp_objs     = constants("dispenser1", type_="resource")
    unloader_objs = constants("unloader1", type_="resource")

    all_resources = (shuttle_objs + parking_objs + loader_objs
                     + disp_objs + unloader_objs)

    # ── Capacity slots per resource ───────────────────────────────────
    # Map each resource object to its capacity (parking has no occupy/release)
    resource_caps = {}
    for obj in shuttle_objs:  resource_caps[obj] = caps["shuttle"]
    for obj in loader_objs:   resource_caps[obj] = caps["loader"]
    for obj in disp_objs:     resource_caps[obj] = caps["dispenser"]
    for obj in unloader_objs: resource_caps[obj] = caps["unloader"]

    all_slots = []
    slot_init = []
    slot_goal = []                     # require all slots restored at goal
    for resource, cap in resource_caps.items():
        slot_names = " ".join(f"{resource.name}_slot{i}" for i in range(cap))
        slots = constants(slot_names, type_="slot")
        all_slots.extend(slots)
        for slot in slots:
            slot_init.append(preds["free_slot"](resource, slot))
            slot_goal.append(preds["free_slot"](resource, slot))

    # ── Initial state ─────────────────────────────────────────────────
    init_facts = (
        # Static type guards
        [preds["is_shuttle"](s) for s in shuttle_objs]
        + [preds["is_loader"](l) for l in loader_objs]
        + [preds["is_dispenser"](d) for d in disp_objs]
        + [preds["is_unloader"](u) for u in unloader_objs]
        # Each shuttle starts at its own parking spot
        + [preds["at"](shuttle_objs[i], parking_objs[i])
           for i in range(len(shuttle_objs))]
        # Capacity tokens — all start free
        + slot_init
        + [preds["operational"](r) for r in all_resources]
    )

    # Goal: all products finished + all capacity slots restored (positive only)
    goal = And(
        *[preds["finished"](p) for p in products],
        *slot_goal,
    )

    return Problem(
        f"production_{n_products}",
        domain=domain,
        objects=list(products) + list(all_resources) + list(all_slots),
        init=init_facts,
        goal=goal,
    )


def main():
    # ── Build domain & problem programmatically ───────────────────────
    domain, preds = build_domain()
    problem = build_problem(domain, preds, n_products=1,
                            capacities={"shuttle": 1, "dispenser": 1})

    print("Domain:", domain.name)
    print("Problem:", problem.name)
    print()

    # ── Solve with PR2 ───────────────────────────────────────────────
    solver = PR2Solver()
    result = solver.solve(domain, problem, timeout=120)

    print(f"Solved:        {result.is_solved}")
    print(f"Strong Cyclic: {result.is_strong_cyclic}")
    print(f"Policy rules:  {len(result.policy)}")
    print(f"FSAPs:         {len(result.fsaps)}")
    print()

    if not result.is_solved:
        print("Solver failed — check stderr:")
        print(result.stderr[-500:] if result.stderr else "(empty)")
        # return

    output_dir = _Planner_ROOT / "output"
    output_dir.mkdir(exist_ok=True)

    rules_path = output_dir / f"{problem.name}_solver_rules.txt"
    lines = [
        f"Domain: {domain.name}",
        f"Problem: {problem.name}",
        f"Solved: {result.is_solved}",
        f"Strong Cyclic: {result.is_strong_cyclic}",
        f"Policy rules: {len(result.policy)}",
        f"FSAPs: {len(result.fsaps)}",
        "",
        "=== POLICY RULES ===",
    ]
    for i, rule in enumerate(result.policy, start=1):
        lines.append(f"[{i}] IF {set(rule.condition)}")
        lines.append(f"    THEN {rule.action}")

    lines.append("")
    lines.append("=== FSAPS ===")
    for i, fsap in enumerate(result.fsaps, start=1):
        lines.append(f"[{i}] IF {set(fsap.condition)}")
        lines.append(f"    FORBID {fsap.action}")

    rules_path.write_text("\n".join(lines) + "\n")
    print(f"Rules written to {rules_path}")

    for rule in result.policy:
        print(f"  IF {set(rule.condition)}")
        print(f"    THEN {rule.action}")
    print()

    # ── Visualize the policy graph ───────────────────────────────────
    if VISUALIZE_POLICY:
        print("=== Policy Visualization ===\n")
        # Create interactive state-transition graph
        graph_path = output_dir / f"{problem.name}_state_graph.html"
        create_force_graph_html(
            result,
            graph_path,
            domain_name=domain.name,
            problem_name=problem.name,
        )
        print(f"🌐 Interactive state graph: {graph_path}")
        print()
    print()

    # ── Generate BT + XML ────────────────────────────────────────────
    bt = policy_to_bt(result)
    print("BT structure:")
    print(bt.pretty())
    print()

    xml = bt_to_xml(bt, tree_id="Production")
    out_path = _Planner_ROOT / "output" / "production.xml"
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(xml)
    print(f"XML written to {out_path}")


if __name__ == "__main__":
    main()
