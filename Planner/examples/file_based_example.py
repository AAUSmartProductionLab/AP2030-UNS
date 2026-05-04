#!/usr/bin/env python3
"""
Example: Solve a FOND problem from PDDL files, generate a grouped
BehaviorTree, export to BehaviorTree.CPP XML, and optionally validate
with the PDDL simulator.

Usage:
    python file_based_example.py [domain_dir] [problem_file]

Defaults to triangle-tireworld/p3.pddl.
"""

import os
import sys
import time
from pathlib import Path

_Planner_ROOT = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_UP_PR2_ROOT = (
    _Planner_ROOT
    / "third_party"
    / "unified-planning"
    / "unified_planning"
    / "engines"
    / "up_pr2"
    / "pr2"
)
_PR2_ROOT = _UP_PR2_ROOT
sys.path.insert(0, str(_PR2_ROOT))
sys.path.insert(0, str(_Planner_ROOT))


from step4_policy_to_bt.builder import build_trivial_bt
from step5_bt_optimization import optimize_bt
from step6_bt_serialization.xml_writer import bt_to_xml
from step3_pddl_solving.solver import solve_from_files
from step3_pddl_solving.visualization import create_force_graph_html


def main():
    # ── Parse arguments ──────────────────────────────────────────────
    domain_dir = sys.argv[1] if len(sys.argv) > 1 else "acrobatics"
    prob_file = sys.argv[2] if len(sys.argv) > 2 else "p3.pddl"

    domain_path = os.path.join(
        str(_PR2_ROOT), f"fond-benchmarks/{domain_dir}/domain.pddl")
    problem_path = os.path.join(
        str(_PR2_ROOT), f"fond-benchmarks/{domain_dir}/{prob_file}")

    if not os.path.exists(problem_path):
        print(f"Problem file not found: {problem_path}")
        return

    print(f"Domain:  {domain_dir}")
    print(f"Problem: {prob_file}")
    print()

    # ── Solve ────────────────────────────────────────────────────────
    result = solve_from_files(domain_path, problem_path, timeout=120)

    print(f"Solved:        {result.is_solved}")
    print(f"Strong Cyclic: {result.is_strong_cyclic}")
    print(f"Policy rules:  {len(result.policy)}")
    print(f"FSAPs:         {len(result.fsaps)}")
    print()

    if not result.is_solved:
        print("No strong-cyclic solution found.")
        return

    policy_result = result.require_policy_result()
    problem_obj = result.metadata.get("problem") if isinstance(result.metadata, dict) else None

    # ── Build trivial BT (Step 4) and optimize (Step 5) ─────────────
    t0 = time.time()
    bt_trivial = build_trivial_bt(policy_result, problem=problem_obj)
    bt = optimize_bt(bt_trivial)
    build_time = time.time() - t0

    print(f"Build time: {build_time:.3f}s")
    print()

    # ── Export XML ───────────────────────────────────────────────────
    safe_name = f"{domain_dir}_{prob_file.replace('.pddl', '')}"

 
    out_dir = os.path.join(_Planner_ROOT, "output")
    os.makedirs(out_dir, exist_ok=True)

    print()

    print("=== Policy Visualization ===\n")
    # Create interactive state-transition graph
    graph_path = Path(out_dir) / f"{prob_file}_state_graph.html"
    create_force_graph_html(
        result,
        graph_path,
        domain_name=domain_dir,
        problem_name=prob_file,
    )
    print(f"🌐 Interactive state graph: {graph_path}")
    print()

    # ── Generate progression BT + XML ───────────────────────────────
    bt2 = bt
    print("\nBT (progression) structure:")
    print(bt2.pretty())
    print()

    xml2 = bt_to_xml(bt2, tree_id="Production")
    out_path2 = Path(out_dir) / f"{safe_name}.xml"
    out_path2.write_text(xml2)
    print(f"XML written to {out_path2}")

if __name__ == "__main__":
    main()
