#!/usr/bin/env python3
"""Run a hoisted-vs-trivial BT equivalence experiment.

This runner evaluates two synthesized BT variants from the same planner policy:
- trivial: one per-rule branch, no condition hoisting
- hoisted: condition-hoisted synthesis pipeline

Primary endpoint:
- solved/not-solved preservation against planner classification

Secondary endpoints:
- ticks to success (mean/median/p95)
- node-ticks to success (mean/median/p95)
- BT node-count reduction with hoisting
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

_Planner_ROOT = Path(__file__).resolve().parents[1]
_REPO_ROOT = _Planner_ROOT.parent

if str(_Planner_ROOT) not in sys.path:
    sys.path.insert(0, str(_Planner_ROOT))
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from bt_synthesis.api import count_bt_nodes, policy_to_bt, policy_to_bt_trivial
from bt_synthesis.simulator import (
    build_global_outcome_probability_provider,
    run_simulation,
)
from pddl_planning.planner_core.solver import solve_from_files


@dataclass(frozen=True)
class BenchmarkInstance:
    domain: str
    problem: str
    domain_path: Path
    problem_path: Path


@dataclass(frozen=True)
class VariantMetrics:
    success_rate: float
    timeout_rate: float
    avg_ticks_success: float
    median_ticks_success: float
    p95_ticks_success: float
    avg_node_ticks_success: float
    median_node_ticks_success: float
    p95_node_ticks_success: float
    successes: int
    failures: int
    timeouts: int
    n_trials: int


def _default_benchmark_root() -> Path:
    return (
        _REPO_ROOT
        / "unified-planning"
        / "unified_planning"
        / "engines"
        / "up_pr2"
        / "pr2"
        / "prp-scripts"
        / "validators"
        / "benchmarks"
    )


def _discover_instances(
    root: Path,
    include_domains: Optional[Sequence[str]] = None,
) -> List[BenchmarkInstance]:
    include = {d.strip() for d in include_domains or [] if d.strip()}
    instances: List[BenchmarkInstance] = []

    for domain_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        if include and domain_dir.name not in include:
            continue

        domain_file = None
        for candidate in ("domain.pddl", "d.pddl"):
            path = domain_dir / candidate
            if path.exists():
                domain_file = path
                break
        if domain_file is None:
            continue

        problems = []
        for pddl in sorted(domain_dir.glob("*.pddl")):
            if pddl.name == domain_file.name:
                continue
            if pddl.name.startswith("p") or pddl.name.startswith("problem"):
                problems.append(pddl)

        for problem_file in problems:
            instances.append(
                BenchmarkInstance(
                    domain=domain_dir.name,
                    problem=problem_file.stem,
                    domain_path=domain_file,
                    problem_path=problem_file,
                )
            )

    return instances


def _percentile(values: Sequence[int], q: float) -> float:
    if not values:
        return 0.0
    if q <= 0:
        return float(min(values))
    if q >= 1:
        return float(max(values))

    ordered = sorted(values)
    idx = int(round((len(ordered) - 1) * q))
    return float(ordered[idx])


def _metrics_from_result(result) -> VariantMetrics:
    timeout_rate = result.timeouts / result.n_trials if result.n_trials else 0.0
    median_ticks = _percentile(result.tick_counts, 0.5)
    p95_ticks = _percentile(result.tick_counts, 0.95)
    median_node_ticks = _percentile(result.node_tick_counts, 0.5)
    p95_node_ticks = _percentile(result.node_tick_counts, 0.95)
    return VariantMetrics(
        success_rate=result.success_rate,
        timeout_rate=timeout_rate,
        avg_ticks_success=result.avg_ticks,
        median_ticks_success=median_ticks,
        p95_ticks_success=p95_ticks,
        avg_node_ticks_success=result.avg_node_ticks,
        median_node_ticks_success=median_node_ticks,
        p95_node_ticks_success=p95_node_ticks,
        successes=result.successes,
        failures=result.failures,
        timeouts=result.timeouts,
        n_trials=result.n_trials,
    )


def _planner_class_label(solve_result) -> str:
    if not solve_result.is_solved:
        return "unsolved_or_weak"
    if solve_result.is_strong_cyclic:
        return "strong_or_strong_cyclic"
    return "solved_unknown_class"


def _bt_is_solved(metrics: VariantMetrics, min_success_rate: float, max_timeout_rate: float) -> bool:
    return (
        metrics.success_rate >= min_success_rate
        and metrics.timeout_rate <= max_timeout_rate
    )


def _iter_profiles(raw_profiles: str) -> Iterable[str]:
    for part in raw_profiles.split(","):
        profile = part.strip()
        if profile:
            yield profile


def _write_csv(path: Path, rows: List[Dict[str, object]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run hoisted vs trivial BT equivalence experiment.")
    parser.add_argument("--benchmarks-root", type=Path, default=_default_benchmark_root())
    parser.add_argument("--domains", type=str, default="", help="Comma-separated domain filter.")
    parser.add_argument("--profiles", type=str, default="uniform,mild_skew,strong_skew")
    parser.add_argument("--trials", type=int, default=2000)
    parser.add_argument("--max-ticks", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=1337)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--backend", type=str, default="pr2", choices=["auto", "pr2", "up"])
    parser.add_argument("--include-non-strong", action="store_true")
    parser.add_argument("--min-success-rate", type=float, default=0.99)
    parser.add_argument("--max-timeout-rate", type=float, default=0.01)
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)

    benchmark_root = args.benchmarks_root
    if not benchmark_root.exists():
        print(f"Benchmark root not found: {benchmark_root}")
        return 2

    domain_filter = [d.strip() for d in args.domains.split(",") if d.strip()]
    instances = _discover_instances(benchmark_root, domain_filter)
    if not instances:
        print("No benchmark instances discovered.")
        return 2

    timestamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    output_dir = args.output_dir or (_Planner_ROOT / "output" / "bt_hoisting_experiments" / timestamp)
    output_dir.mkdir(parents=True, exist_ok=True)

    episode_rows: List[Dict[str, object]] = []
    summary_rows: List[Dict[str, object]] = []
    skipped_rows: List[Dict[str, object]] = []

    profiles = list(_iter_profiles(args.profiles))

    print(f"Discovered instances: {len(instances)}")
    print(f"Profiles: {profiles}")
    print(f"Output: {output_dir}")

    for instance_index, instance in enumerate(instances):
        print(f"[{instance_index + 1}/{len(instances)}] Solving {instance.domain}/{instance.problem} ...")
        try:
            solve_result = solve_from_files(
                instance.domain_path,
                instance.problem_path,
                backend=args.backend,
                timeout=args.timeout,
            )
        except Exception as exc:
            skipped_rows.append(
                {
                    "domain": instance.domain,
                    "problem": instance.problem,
                    "reason": "solve_or_parse_error",
                    "status": "error",
                    "planner_class": type(exc).__name__,
                }
            )
            print(f"  Skipping due to solve/parse error: {type(exc).__name__}: {exc}")
            continue

        planner_class = _planner_class_label(solve_result)
        policy_count = len(getattr(solve_result, "policy", [])) if solve_result.is_policy else 0

        if not solve_result.is_policy or not solve_result.is_solved or policy_count == 0:
            skipped_rows.append(
                {
                    "domain": instance.domain,
                    "problem": instance.problem,
                    "reason": "no_policy_or_unsolved",
                    "status": solve_result.status,
                    "planner_class": planner_class,
                }
            )
            continue

        if not args.include_non_strong and not solve_result.is_strong_cyclic:
            skipped_rows.append(
                {
                    "domain": instance.domain,
                    "problem": instance.problem,
                    "reason": "non_strong_filtered",
                    "status": solve_result.status,
                    "planner_class": planner_class,
                }
            )
            continue

        problem_obj = solve_result.metadata.get("problem") if isinstance(solve_result.metadata, dict) else None
        policy_result = solve_result.require_policy_result()

        hoisted_bt = policy_to_bt(policy_result, problem=problem_obj)
        trivial_bt = policy_to_bt_trivial(policy_result, problem=problem_obj)

        hoisted_nodes = count_bt_nodes(hoisted_bt.root)
        trivial_nodes = count_bt_nodes(trivial_bt.root)

        domain_pddl = getattr(policy_result, "domain_pddl", "") or ""
        problem_pddl = getattr(policy_result, "problem_pddl", "") or ""
        if not domain_pddl or not problem_pddl:
            skipped_rows.append(
                {
                    "domain": instance.domain,
                    "problem": instance.problem,
                    "reason": "missing_pddl_payload",
                    "status": solve_result.status,
                    "planner_class": planner_class,
                }
            )
            continue

        for profile_index, profile in enumerate(profiles):
            provider = build_global_outcome_probability_provider(profile)
            paired_seed = int(args.seed + (instance_index * 1000) + (profile_index * 100000))

            variant_results: Dict[str, VariantMetrics] = {}
            for variant_name, bt in (("trivial", trivial_bt), ("hoisted", hoisted_bt)):

                def _on_episode(trial: int, success: bool, ticks: int, node_ticks: int) -> None:
                    timeout = (not success) and ticks >= args.max_ticks
                    episode_rows.append(
                        {
                            "domain": instance.domain,
                            "problem": instance.problem,
                            "profile": profile,
                            "seed": paired_seed,
                            "variant": variant_name,
                            "trial": trial,
                            "success": int(success),
                            "timeout": int(timeout),
                            "ticks": ticks,
                            "node_ticks": node_ticks,
                        }
                    )

                sim_result = run_simulation(
                    bt,
                    domain_pddl,
                    problem_pddl,
                    n_trials=args.trials,
                    max_ticks=args.max_ticks,
                    seed=paired_seed,
                    on_episode=_on_episode,
                    outcome_probability_provider=provider,
                )
                variant_results[variant_name] = _metrics_from_result(sim_result)

            trivial_metrics = variant_results["trivial"]
            hoisted_metrics = variant_results["hoisted"]

            trivial_solved = _bt_is_solved(
                trivial_metrics,
                args.min_success_rate,
                args.max_timeout_rate,
            )
            hoisted_solved = _bt_is_solved(
                hoisted_metrics,
                args.min_success_rate,
                args.max_timeout_rate,
            )
            expected_solved = planner_class == "strong_or_strong_cyclic"

            summary_rows.append(
                {
                    "domain": instance.domain,
                    "problem": instance.problem,
                    "profile": profile,
                    "seed": paired_seed,
                    "planner_status": solve_result.status,
                    "planner_class": planner_class,
                    "expected_solved": int(expected_solved),
                    "trivial_solved": int(trivial_solved),
                    "hoisted_solved": int(hoisted_solved),
                    "variants_agree": int(trivial_solved == hoisted_solved),
                    "trivial_success_rate": trivial_metrics.success_rate,
                    "hoisted_success_rate": hoisted_metrics.success_rate,
                    "trivial_timeout_rate": trivial_metrics.timeout_rate,
                    "hoisted_timeout_rate": hoisted_metrics.timeout_rate,
                    "trivial_avg_ticks_success": trivial_metrics.avg_ticks_success,
                    "hoisted_avg_ticks_success": hoisted_metrics.avg_ticks_success,
                    "trivial_median_ticks_success": trivial_metrics.median_ticks_success,
                    "hoisted_median_ticks_success": hoisted_metrics.median_ticks_success,
                    "trivial_p95_ticks_success": trivial_metrics.p95_ticks_success,
                    "hoisted_p95_ticks_success": hoisted_metrics.p95_ticks_success,
                    "trivial_avg_node_ticks_success": trivial_metrics.avg_node_ticks_success,
                    "hoisted_avg_node_ticks_success": hoisted_metrics.avg_node_ticks_success,
                    "trivial_median_node_ticks_success": trivial_metrics.median_node_ticks_success,
                    "hoisted_median_node_ticks_success": hoisted_metrics.median_node_ticks_success,
                    "trivial_p95_node_ticks_success": trivial_metrics.p95_node_ticks_success,
                    "hoisted_p95_node_ticks_success": hoisted_metrics.p95_node_ticks_success,
                    "trivial_nodes": trivial_nodes,
                    "hoisted_nodes": hoisted_nodes,
                    "node_reduction": (trivial_nodes - hoisted_nodes),
                    "node_reduction_ratio": (
                        (trivial_nodes - hoisted_nodes) / trivial_nodes if trivial_nodes else 0.0
                    ),
                    "class_preserved_trivial": int(trivial_solved == expected_solved),
                    "class_preserved_hoisted": int(hoisted_solved == expected_solved),
                }
            )

    summary_fields = [
        "domain",
        "problem",
        "profile",
        "seed",
        "planner_status",
        "planner_class",
        "expected_solved",
        "trivial_solved",
        "hoisted_solved",
        "variants_agree",
        "trivial_success_rate",
        "hoisted_success_rate",
        "trivial_timeout_rate",
        "hoisted_timeout_rate",
        "trivial_avg_ticks_success",
        "hoisted_avg_ticks_success",
        "trivial_median_ticks_success",
        "hoisted_median_ticks_success",
        "trivial_p95_ticks_success",
        "hoisted_p95_ticks_success",
        "trivial_avg_node_ticks_success",
        "hoisted_avg_node_ticks_success",
        "trivial_median_node_ticks_success",
        "hoisted_median_node_ticks_success",
        "trivial_p95_node_ticks_success",
        "hoisted_p95_node_ticks_success",
        "trivial_nodes",
        "hoisted_nodes",
        "node_reduction",
        "node_reduction_ratio",
        "class_preserved_trivial",
        "class_preserved_hoisted",
    ]
    _write_csv(output_dir / "summary.csv", summary_rows, summary_fields)

    episode_fields = [
        "domain",
        "problem",
        "profile",
        "seed",
        "variant",
        "trial",
        "success",
        "timeout",
        "ticks",
        "node_ticks",
    ]
    _write_csv(output_dir / "episodes.csv", episode_rows, episode_fields)

    skipped_fields = ["domain", "problem", "reason", "status", "planner_class"]
    _write_csv(output_dir / "skipped.csv", skipped_rows, skipped_fields)

    metadata = {
        "timestamp": timestamp,
        "benchmarks_root": str(benchmark_root),
        "domains_filter": domain_filter,
        "profiles": profiles,
        "trials": args.trials,
        "max_ticks": args.max_ticks,
        "seed": args.seed,
        "backend": args.backend,
        "timeout": args.timeout,
        "include_non_strong": args.include_non_strong,
        "min_success_rate": args.min_success_rate,
        "max_timeout_rate": args.max_timeout_rate,
        "num_instances_discovered": len(instances),
        "num_rows_summary": len(summary_rows),
        "num_rows_episodes": len(episode_rows),
        "num_rows_skipped": len(skipped_rows),
    }
    (output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    print("Done.")
    print(f"Summary rows: {len(summary_rows)}")
    print(f"Episode rows: {len(episode_rows)}")
    print(f"Skipped rows: {len(skipped_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
