#!/usr/bin/env python3
"""
Example: Visualize a PR2 policy before converting to behavior tree.

This example shows how to:
1. Solve a FOND problem with PR2
2. Visualize the policy as an interactive HTML state-transition graph
3. Convert to a behavior tree

The visualization helps understand the policy structure before
committing to a specific BT architecture.
"""

import sys
from pathlib import Path

_Planner_ROOT = Path(__file__).resolve().parent.parent
_PR2_ROOT = _Planner_ROOT / "pr2"
sys.path.insert(0, str(_Planner_ROOT))

from pddl_planning.planner_core.solver import solve_from_files
from pddl_planning.pr2_bridge.visualization import create_force_graph_html


def main():
    """Solve and visualize a simple domain."""
    
    # Use existing domain/problem files
    domain_path = _PR2_ROOT / "fond-benchmarks" / "triangle-tireworld" / "domain.pddl"
    problem_path = _PR2_ROOT / "fond-benchmarks" / "triangle-tireworld" / "p6.pddl"
    
    if not domain_path.exists():
        print(f"Domain not found: {domain_path}")
        return
    
    print(f"Domain:  {domain_path.name}")
    print(f"Problem: {problem_path.name}")
    print()
    
    # Solve with PR2
    result = solve_from_files(str(domain_path), str(problem_path), timeout=30)
    
    print(f"✓ Solved:        {result.is_solved}")
    print(f"🔄 Strong Cyclic: {result.is_strong_cyclic}")
    print(f"📝 Policy rules:  {len(result.policy)}")
    print(f"🚫 FSAPs:         {len(result.fsaps)}")
    print()
    
    if not result.is_solved:
        print("❌ Solver failed")
        return
    
    # ══════════════════════════════════════════════════════════════════
    # Create interactive HTML state-transition graph
    # ══════════════════════════════════════════════════════════════════
    
    output_dir = _PR2_ROOT / "output"
    output_dir.mkdir(exist_ok=True)
    
    force_graph_file = output_dir / "policy_force_graph.html"
    create_force_graph_html(
        result, 
        force_graph_file,
        domain_name=domain_path.stem,
        problem_name=problem_path.stem
    )
    print(f"🌐 Created interactive state-transition graph: {force_graph_file}")
    print(f"   Open this in your browser to inspect policy states and action transitions!")
    print()
    
    # Show sample rules in text form
    print("📋 Sample Policy Rules")
    print("-" * 60)
    for i, rule in enumerate(result.policy[:5], 1):
        print(f"{i}. IF {len(rule.condition)} conditions:")
        for cond in sorted(list(rule.condition)[:3]):
            print(f"      • {cond}")
        if len(rule.condition) > 3:
            print(f"      ... and {len(rule.condition)-3} more")
        print(f"   THEN: {rule.action}")
        print()
    
    if len(result.policy) > 5:
        print(f"   ... and {len(result.policy)-5} more rules")
    
    print()
    print("=" * 60)
    print("✅ Visualization complete!")
    print("=" * 60)
    print()
    print("Next steps:")
    print("  1. Open the HTML file in your browser for the interactive graph")
    print("  2. Review the policy structure")
    print("  3. Convert to BT: bt = policy_to_bt(result)")
    print("=" * 60)


if __name__ == "__main__":
    main()
