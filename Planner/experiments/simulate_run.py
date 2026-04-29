#!/usr/bin/env python3
"""Run the BT Monte-Carlo simulator against a saved planner run directory.

Usage:
    python -m Planner.experiments.simulate_run <run_dir> [--trials N] [--max-ticks N] [--seed N]

Where ``<run_dir>`` contains ``domain.pddl`` and ``problem.pddl`` from a
``Planner/output/ai_planning_runs/<TIMESTAMP>`` directory.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

_PLANNER_ROOT = Path(__file__).resolve().parents[1]
_REPO_ROOT = _PLANNER_ROOT.parent
_PR2_ROOT = (
    _REPO_ROOT
    / "unified-planning"
    / "unified_planning"
    / "engines"
    / "up_pr2"
    / "pr2"
)
sys.path.insert(0, str(_PR2_ROOT))
sys.path.insert(0, str(_PLANNER_ROOT))

from bt_synthesis.api import policy_to_bt, policy_to_bt_trivial  # noqa: E402
from bt_synthesis.simulator import run_simulation  # noqa: E402
from pddl_planning.planner_core.solver import solve_from_files  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--trials", type=int, default=100)
    ap.add_argument("--max-ticks", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=12345)
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--backend", default="pr2")
    ap.add_argument("--variant", choices=["hoisted", "trivial", "both"], default="both")
    args = ap.parse_args()

    run_dir = Path(args.run_dir)
    domain = run_dir / "domain.pddl"
    problem = run_dir / "problem.pddl"
    if not domain.is_file() or not problem.is_file():
        print(f"missing domain/problem in {run_dir}", file=sys.stderr)
        return 2

    print(f"Run directory : {run_dir}")
    print(f"Trials        : {args.trials}")
    print(f"Max ticks     : {args.max_ticks}")
    print(f"Seed          : {args.seed}")
    print()

    print("Solving (FOND) ...")
    t0 = time.time()
    solve_result = solve_from_files(
        str(domain),
        str(problem),
        backend=args.backend,
        timeout=args.timeout,
    )
    solve_dt = time.time() - t0
    print(f"  solved={solve_result.is_solved} strong_cyclic={solve_result.is_strong_cyclic} "
          f"policy_rules={len(getattr(solve_result, 'policy', [])) } in {solve_dt:.2f}s")
    if not solve_result.is_solved:
        print("Cannot simulate – planner did not return a policy.")
        return 1

    problem_obj = (solve_result.metadata.get("problem")
                   if isinstance(solve_result.metadata, dict) else None)
    policy_result = solve_result.require_policy_result()

    print("Building BT(s) ...")
    variants: list[tuple[str, object]] = []
    if args.variant in ("hoisted", "both"):
        t0 = time.time()
        variants.append(("hoisted", policy_to_bt(policy_result, problem=problem_obj)))
        print(f"  hoisted built in {time.time() - t0:.2f}s")
    if args.variant in ("trivial", "both"):
        t0 = time.time()
        variants.append(("trivial", policy_to_bt_trivial(policy_result, problem=problem_obj)))
        print(f"  trivial built in {time.time() - t0:.2f}s")

    domain_pddl = getattr(policy_result, "domain_pddl", "") or domain.read_text()
    problem_pddl = getattr(policy_result, "problem_pddl", "") or problem.read_text()

    summaries = []
    for name, bt in variants:
        last_print = [time.time()]

        def _on_episode(trial: int, success: bool, ticks: int, node_ticks: int) -> None:
            now = time.time()
            if trial < 3 or trial % 25 == 0 or (now - last_print[0]) > 5.0:
                tag = "OK " if success else "FAIL"
                print(f"  [{name}] trial {trial:4d}: {tag} ticks={ticks} node_ticks={node_ticks}")
                last_print[0] = now

        print(f"\nRunning {name} simulation ({args.trials} trials) ...")
        t0 = time.time()
        result = run_simulation(
            bt,
            domain_pddl,
            problem_pddl,
            n_trials=args.trials,
            max_ticks=args.max_ticks,
            seed=args.seed,
            on_episode=_on_episode,
        )
        sim_dt = time.time() - t0
        summaries.append((name, result, sim_dt))

    print()
    print("=== Simulation summary ===")
    for name, result, sim_dt in summaries:
        rate = result.successes / result.n_trials if result.n_trials else 0.0
        avg = (sum(result.tick_counts) / len(result.tick_counts)) if result.tick_counts else 0.0
        print(f"  [{name}] success={result.successes}/{result.n_trials} ({rate:.1%}) "
              f"failures={result.failures} timeouts={result.timeouts} "
              f"avg_ticks={avg:.1f} wall={sim_dt:.2f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
