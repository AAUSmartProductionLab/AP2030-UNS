#!/usr/bin/env python3
"""
BOP-Driven FOND Domain with Individual Resource Actions
========================================================

Demonstrates a **product-agnostic** PDDL domain for aseptic production.
The production sequence is NOT hardcoded into action schemas — instead it
is derived from the Product's **Bill of Process (BOP)** and injected as
init facts in the problem instance.

Each Resource AAS provides its own action (``dispense``, ``stopper``,
``quality_control``, etc.) with resource-specific failure modes.
The Product AAS provides the BOP as an ordered list of steps.

BOP ordering is enforced through a **derived predicate** (PDDL axiom):

  * ``step_ready(p, step)`` is derived: true when there exists a predecessor
    step that is done and precedes this step.
  * A dummy ``s_start`` step (done in init) bootstraps the first action.
  * Process actions simply check ``step_ready(p, step)`` — no ``prev``
    parameter needed.

Infrastructure operations are **causally inferred** by the planner:

  * Process actions require ``product_at(p, sp)`` -> planner needs ``move``
  * ``move`` requires ``on(c, p)`` -> planner needs ``load``
  * ``finished(p)`` in goal -> planner needs ``unload``
  * ``unload`` requires ``last_step(step) & step_done(p, step)``

Key design:
  * ``occupy_station`` / ``release_station`` -- generic for ALL stations.
  * ``occupy_transport`` / ``release_transport`` -- shuttle reservation.
  * Per-resource actions (``load_loader1``, ``process_dispenser1``, etc.)
    -- each Resource AAS contributes an action with itself baked in as a
    PDDL constant.  The planner decides *when*, not *which resource*.
  * ``move`` and ``repair`` are unchanged infrastructure actions.
  * ``build_domain`` accepts a resource catalog and generates per-resource
    actions + domain constants automatically.

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
from pddl.logic.base import And, Not, OneOf, ExistsCondition
from pddl.logic.effects import When
from pddl.logic.predicates import DerivedPredicate
from pddl.requirements import Requirements

from pr2_adapter import PR2Solver
from pr2_to_bt import policy_to_bt, bt_to_xml
from visualize_policy_graph import create_force_graph_html

# Flag to enable/disable interactive visualization
VISUALIZE_POLICY = True


# ===================================================================
#  BOP DEFINITION  (mirrors the Product AAS BillOfProcesses submodel)
# ===================================================================

# The BOP contains ONLY product-specific process steps.
# Infrastructure (loading onto shuttle, unloading, transport) is NOT
# listed here -- the planner infers it through causal precondition chains.

HGH_BOP = [
    {"step": "dispensing",  "capability": "dispensing"},
]

# Alternate BOP -- more steps, same domain
HGH_FULL_BOP = [
    {"step": "dispensing",   "capability": "dispensing"},
    {"step": "stoppering",   "capability": "stoppering"},
    {"step": "inspection",   "capability": "quality_ctrl"},
]

# Resource catalog -- maps capability name -> list of (resource_name, capacity)
# In the full pipeline this comes from the Resource AAS configs.
# "loading" and "unloading" are infrastructure capabilities.
RESOURCE_CATALOG = {
    "loading":      [("loader1", 1)],
    "dispensing":   [("dispenser1", 1)],
    "stoppering":   [("stopperer1", 1)],
    "quality_ctrl": [("camera1", 1)],
    "unloading":    [("unloader1", 1)],
}


def build_domain(resource_catalog=None):
    """Build an aseptic production domain with per-resource actions.

    Each Resource AAS contributes its own action with itself baked in as
    a PDDL domain constant -- the planner decides *when* to invoke it,
    not *which resource* to bind.

    A derived predicate ``step_ready(p, step)`` encapsulates the
    predecessor check (exists prev: step_precedes(prev, step) &
    step_done(p, prev)).  Process actions simply check step_ready.
    A dummy ``s_start`` step bootstraps the chain.

    Generic infrastructure actions (occupy, release, move, repair) keep
    variable parameters.  Resource-specific actions (load, unload,
    process) have their resource and capability baked in.
    """
    if resource_catalog is None:
        resource_catalog = RESOURCE_CATALOG

    # -- Typed variables (for generic actions and predicate defs) ------
    [r]      = variables("r",      types=["resource"])      # any resource
    [c]      = variables("c",      types=["shuttle"])        # shuttle (transport)
    [s]      = variables("s",      types=["station"])        # any station
    [s1]     = variables("s1",     types=["station"])        # move: from
    [s2]     = variables("s2",     types=["station"])        # move: to
    [p]      = variables("p",      types=["product"])
    [step]   = variables("step",   types=["step"])
    [prev]   = variables("prev",   types=["step"])           # used in derived predicate
    [cap]    = variables("cap",    types=["capability"])     # for predicate definition

    # -- Static predicates (set once in init, never modified) ----------
    step_requires  = Predicate("step_requires", step, cap)  # BOP step needs this capability
    step_precedes  = Predicate("step_precedes", step, prev)  # BOP ordering: 1st precedes 2nd
    last_step      = Predicate("last_step", step)      # final BOP step (gates unload)

    # -- Dynamic predicates --------------------------------------------
    occupied       = Predicate("occupied", r, p)       # resource reserved for product
    operational    = Predicate("operational", r)       # resource is working
    on             = Predicate("on", c, p)             # product physically on shuttle
    at             = Predicate("at", c, s)             # shuttle at station
    product_at     = Predicate("product_at", p, s)     # product at station (tracks with shuttle)
    step_done      = Predicate("step_done", p, step)   # product completed this BOP step
    finished       = Predicate("finished", p)          # product complete (unloaded)

    # -- Derived predicate: step_ready ---------------------------------
    # True when there exists a predecessor step that is done and precedes
    # this step.  Eliminates the need for a ``prev`` action parameter.
    step_ready     = Predicate("step_ready", p, step)
    step_ready_axiom = DerivedPredicate(
        predicate=step_ready,
        condition=ExistsCondition(
            cond=step_precedes(prev, step) & step_done(p, prev),
            variables=[prev],
        ),
    )

    predicates = [
        step_requires, step_precedes, last_step,
        occupied, operational, on, at, product_at,
        step_done, step_ready, finished,
    ]

    # ==================================================================
    #  GENERIC ACTIONS (infrastructure -- not resource-specific)
    # ==================================================================

    # -- Occupy station (generic -- loader, process, unloader) ---------
    occupy_station = Action(
        "occupy_station",
        parameters=[s, p, c],
        precondition=(
            operational(s)
            & ~occupied(s, p)
            & occupied(c, p)
        ),
        effect=occupied(s, p),
    )

    # -- Occupy transport (shuttle) ------------------------------------
    occupy_transport = Action(
        "occupy_transport",
        parameters=[c, p],
        precondition=operational(c),
        effect=occupied(c, p),
    )

    # -- Release station (generic) -------------------------------------
    # No step-done guard.  The planner won't release prematurely because
    # load/process/unload all require occupied(s, p) -- releasing before
    # the action executes makes it impossible, creating a dead-end.
    release_station = Action(
        "release_station",
        parameters=[s, p],
        precondition=(
            occupied(s, p) & operational(s)
        ),
        effect=~occupied(s, p)
    )

    # -- Release transport (shuttle) -----------------------------------
    release_transport = Action(
        "release_transport",
        parameters=[c, p],
        precondition=(
            occupied(c, p) & operational(c)
            & finished(p) & ~on(c, p)
        ),
        effect=~occupied(c, p)
    )

    # -- Move shuttle between stations ---------------------------------
    moveToStation = Action(
        "move",
        parameters=[c, s1, s2, p],
        precondition=(
            at(c, s1) & occupied(c, p)
            & occupied(s2, p) & operational(c)
        ),
        effect=(
            ~at(c, s1) & at(c, s2)
            & When(on(c, p), ~product_at(p, s1) & product_at(p, s2))
        ),
    )

    # -- Repair: recover from breakdown --------------------------------
    repair = Action(
        "repair",
        parameters=[r],
        precondition=~operational(r),
        effect=operational(r),
    )

    # ==================================================================
    #  PER-RESOURCE ACTIONS (from Resource AAS descriptions)
    # ==================================================================
    # Each Resource AAS contributes an action with itself baked in as a
    # PDDL domain constant.  The planner decides *when* to invoke it,
    # not *which resource* to bind.

    domain_consts = []        # PDDL constants for the domain
    resource_actions = []     # per-resource Action objects
    all_resource_consts = []  # flat list for operational() init facts
    cap_consts = {}           # capability name -> constant object

    # -- Capability constants ------------------------------------------
    process_caps = sorted(
        k for k in resource_catalog if k not in ("loading", "unloading")
    )
    for cap_name in process_caps:
        [cap_c] = constants(f"cap_{cap_name}", type_="capability")
        cap_consts[cap_name] = cap_c
        domain_consts.append(cap_c)

    # -- Loading actions (one per loader from the catalog) -------------
    for res_name, _ in resource_catalog.get("loading", []):
        [res_c] = constants(res_name, type_="loader")
        domain_consts.append(res_c)
        all_resource_consts.append(res_c)
        resource_actions.append(Action(
            f"load_{res_name}",
            parameters=[p, c],
            precondition=(
                at(c, res_c) & occupied(c, p) & occupied(res_c, p)
                & ~on(c, p)
                & operational(res_c) & operational(c)
            ),
            effect=OneOf(
                on(c, p) & product_at(p, res_c),
                ~operational(res_c),
                on(c, p) & product_at(p, res_c) & ~operational(res_c),
            ),
        ))

    # -- Unloading actions (one per unloader from the catalog) ---------
    for res_name, _ in resource_catalog.get("unloading", []):
        [res_c] = constants(res_name, type_="unloader")
        domain_consts.append(res_c)
        all_resource_consts.append(res_c)
        resource_actions.append(Action(
            f"unload_{res_name}",
            parameters=[p, c, step],
            precondition=(
                on(c, p) & at(c, res_c) & occupied(res_c, p) & occupied(c, p)
                & last_step(step) & step_done(p, step)
                & operational(res_c) & operational(c)
            ),
            effect=OneOf(
                ~on(c, p) & finished(p),
                ~on(c, p) & finished(p) & ~operational(res_c),
                ~operational(res_c),
            ),
        ))

    # -- Process actions (one per process station from the catalog) ----
    # Each process station provides exactly one capability, baked in.
    for cap_name in process_caps:
        for res_name, _ in resource_catalog[cap_name]:
            [res_c] = constants(res_name, type_="process_station")
            domain_consts.append(res_c)
            all_resource_consts.append(res_c)
            resource_actions.append(Action(
                f"process_{res_name}",
                parameters=[p, step],
                precondition=(
                    step_requires(step, cap_consts[cap_name])
                    & step_ready(p, step)
                    & ~step_done(p, step)
                    & product_at(p, res_c) & occupied(res_c, p)
                    & operational(res_c)
                ),
                effect=OneOf(
                    step_done(p, step),
                    step_done(p, step) & ~operational(res_c),
                    ~operational(res_c),
                ),
            ))

    actions = [
        occupy_station, occupy_transport,
        release_station, release_transport,
        moveToStation, repair,
    ] + resource_actions

    # -- Domain --------------------------------------------------------
    domain = Domain(
        "aseptic_production_bop",
        requirements=[Requirements.STRIPS, Requirements.TYPING,
                      Requirements.NON_DETERMINISTIC,
                      Requirements.CONDITIONAL_EFFECTS,
                      Requirements.DERIVED_PREDICATES],
        types={
            "thing": None,
            "product": "thing",
            "resource": "thing",
            "shuttle": "resource",
            "station": "resource",
            "loader": "station",
            "unloader": "station",
            "process_station": "station",
            "step": None,
            "capability": None,
        },
        constants=domain_consts,
        predicates=predicates,
        derived_predicates=[step_ready_axiom],
        actions=actions,
    )

    preds = {
        "step_requires": step_requires, "step_precedes": step_precedes,
        "last_step": last_step,
        "step_done": step_done, "step_ready": step_ready,
        "occupied": occupied, "operational": operational,
        "on": on, "at": at,
        "product_at": product_at,
        "finished": finished,
    }

    domain_resources = {
        "all": all_resource_consts,
        "capabilities": cap_consts,
    }

    return domain, preds, domain_resources


def build_problem(domain, preds, domain_resources, bop,
                  n_products=1, n_shuttles=1):
    """Build a problem instance from a product BOP.

    Resources and capabilities are domain constants (generated by
    ``build_domain`` from the Resource AAS catalog).  The problem adds
    products, shuttles, parking spots, and BOP steps.

    Parameters
    ----------
    domain : pddl.core.Domain
    preds : dict of predicates returned by build_domain
    domain_resources : dict
        ``{"all": [resource consts], "capabilities": {name: const}}``
    bop : list[dict]
        Product-specific process steps.  Each dict:
          {"step": str, "capability": str}
    n_products : int
    n_shuttles : int
    """
    # -- Products ------------------------------------------------------
    products = constants(
        " ".join(f"p{i}" for i in range(n_products)), type_="product"
    )

    # -- Shuttles + parking spots --------------------------------------
    shuttle_objs = constants(
        " ".join(f"shuttle{i}" for i in range(n_shuttles)), type_="shuttle"
    )
    parking_objs = constants(
        " ".join(f"parking{i}" for i in range(n_shuttles + 1)), type_="station"
    )

    # -- BOP steps (PDDL objects) --------------------------------------
    # Includes a dummy "start" step to bootstrap the precondition chain.
    step_names = ["start"] + [entry["step"] for entry in bop]
    bop_steps = constants(
        " ".join(f"s_{name}" for name in step_names), type_="step"
    )
    step_obj = {name: obj for name, obj in zip(step_names, bop_steps)}

    cap_consts = domain_resources["capabilities"]

    # -- Static BOP facts ----------------------------------------------
    static_facts = []

    # BOP step_requires
    for entry in bop:
        static_facts.append(
            preds["step_requires"](step_obj[entry["step"]],
                                   cap_consts[entry["capability"]])
        )

    # BOP step_precedes (sequential ordering from list position)
    static_facts.append(
        preds["step_precedes"](step_obj["start"],
                               step_obj[bop[0]["step"]])
    )
    for i in range(len(bop) - 1):
        static_facts.append(
            preds["step_precedes"](step_obj[bop[i]["step"]],
                                   step_obj[bop[i+1]["step"]])
        )

    # last_step -- gates the unload action
    last_bop_step = bop[-1]["step"]
    static_facts.append(preds["last_step"](step_obj[last_bop_step]))

    # -- Dynamic initial state -----------------------------------------
    # Resources are domain constants but still need operational() in init
    all_resources = (
        list(shuttle_objs) + list(parking_objs)
        + domain_resources["all"]
    )

    init_facts = (
        # Shuttle starting positions
        [preds["at"](shuttle_objs[i], parking_objs[i])
           for i in range(n_shuttles)]
        # All resources start operational
        + [preds["operational"](r) for r in all_resources]
        # Static BOP facts
        + static_facts
        # Each product starts with the dummy "start" step done
        + [preds["step_done"](prod, step_obj["start"])
           for prod in products]
    )

    # -- Goal ----------------------------------------------------------
    goal = And(
        *[preds["finished"](prod) for prod in products]
    )

    # Objects: products, shuttles, parking, BOP steps
    # (resources and capabilities are domain constants)
    all_objects = (
        list(products) + list(shuttle_objs) + list(parking_objs)
        + list(bop_steps)
    )

    return Problem(
        f"production_bop_{n_products}p",
        domain=domain,
        objects=all_objects,
        init=init_facts,
        goal=goal,
    )


def main():
    # -- Build domain (resource-specific actions from catalog) ---------
    domain, preds, domain_resources = build_domain()

    # -- Build problem from BOP ----------------------------------------
    problem = build_problem(
        domain, preds, domain_resources,
        bop=HGH_BOP,
        n_products=1,
        n_shuttles=1,
    )

    print("Domain:", domain.name)
    print("Problem:", problem.name)
    print(f"BOP (product-specific only): {[s['step'] for s in HGH_BOP]}")
    print(f"  load/unload/move/repair = causally inferred by planner")
    print()

    # -- Solve with PR2 -----------------------------------------------
    solver = PR2Solver()
    result = solver.solve(domain, problem, timeout=120)

    print(f"Solved:        {result.is_solved}")
    print(f"Strong Cyclic: {result.is_strong_cyclic}")
    print(f"Policy rules:  {len(result.policy)}")
    print(f"FSAPs:         {len(result.fsaps)}")
    print()

    if not result.is_solved:
        print("Solver failed -- check stderr:")
        print(result.stderr[-500:] if result.stderr else "(empty)")
        # return  # continue to generate BT from weak policy

    output_dir = _Planner_ROOT / "output"
    output_dir.mkdir(exist_ok=True)

    # -- Write solver rules --------------------------------------------
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

    # -- Visualize the policy graph ------------------------------------
    if VISUALIZE_POLICY:
        print("=== Policy Visualization ===\n")
        graph_path = output_dir / f"{problem.name}_state_graph.html"
        create_force_graph_html(
            result, graph_path,
            domain_name=domain.name,
            problem_name=problem.name,
        )
        print(f"Interactive state graph: {graph_path}")
        print()

    # -- Generate BT + XML ---------------------------------------------
    bt = policy_to_bt(result)
    print("BT structure:")
    print(bt.pretty())
    print()

    xml = bt_to_xml(bt, tree_id="ProductionBOP")
    out_path = output_dir / f"{problem.name}_production.xml"
    out_path.write_text(xml)
    print(f"XML written to {out_path}")

    # ==================================================================
    #  ALTERNATE BOP -- domain stays the SAME, only problem changes
    # ==================================================================
    print("\n" + "=" * 70)
    print("  ALTERNATE BOP: dispensing + stoppering + inspection")
    print("=" * 70 + "\n")

    problem2 = build_problem(
        domain, preds, domain_resources,
        bop=HGH_FULL_BOP,
        n_products=1,
        n_shuttles=1,
    )

    print("Domain:", domain.name, "(unchanged)")
    print("Problem:", problem2.name)
    print(f"BOP (product-specific only): {[s['step'] for s in HGH_FULL_BOP]}")
    print(f"  load/unload/move/repair = causally inferred by planner")
    print()

    result2 = solver.solve(domain, problem2, timeout=180)

    print(f"Solved:        {result2.is_solved}")
    print(f"Strong Cyclic: {result2.is_strong_cyclic}")
    print(f"Policy rules:  {len(result2.policy)}")
    print(f"FSAPs:         {len(result2.fsaps)}")
    print()

    if result2.policy:
        bt2 = policy_to_bt(result2)
        xml2 = bt_to_xml(bt2, tree_id="ProductionBOP_Full")
        out_path2 = output_dir / f"{problem2.name}_full_production.xml"
        out_path2.write_text(xml2)
        print(f"XML written to {out_path2}")
    else:
        print("No policy -- skipping BT generation for alternate BOP.")


if __name__ == "__main__":
    main()
