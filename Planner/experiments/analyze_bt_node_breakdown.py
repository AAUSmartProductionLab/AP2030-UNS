#!/usr/bin/env python3
"""Per-category node-tick breakdown for hoisted vs trivial BTs.

For every benchmark instance under the standard PR2 fond-benchmarks
directory (or a custom root via ``--benchmarks-root``), this script:

  1. Solves the problem with the configured backend.
  2. Builds the hoisted and trivial BT variants from the same policy.
  3. Counts BT nodes statically by category (action, condition,
     selector, sequence, decorator, leaf).
  4. Runs a limited number of simulated episodes per profile with a
     visitor that bins every behaviour visit by py_trees node category,
     producing per-tick-time category totals.

Outputs:
  - ``node_breakdown.csv`` — one row per (instance, profile, variant)
    with static counts, dynamic visit counts, ticks, success/timeout.
  - ``fig_node_breakdown_static.png`` — stacked bars of static node
    counts per variant per instance.
  - ``fig_node_breakdown_dynamic.png`` — stacked bars of avg per-episode
    visits by category, paired trivial vs hoisted per instance.
  - ``fig_condition_vs_wrapper_tradeoff.png`` — scatter:
    Δ(condition visits, hoisted - trivial)  vs
    Δ(wrapper visits, hoisted - trivial),
    annotated with instance names. Below-diagonal points (in the negative
    quadrant) are pure wins for hoisting; the line ``y = -x`` separates
    "savings outweigh overhead" from "overhead dominates".
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import py_trees
import seaborn as sns

_Planner_ROOT = Path(__file__).resolve().parents[1]
_REPO_ROOT = _Planner_ROOT.parent
if str(_Planner_ROOT) not in sys.path:
    sys.path.insert(0, str(_Planner_ROOT))
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from bt_synthesis.api import policy_to_bt, policy_to_bt_trivial
from bt_synthesis.simulator import (
    NodeTickCountVisitor,  # noqa: F401  (kept for reference / parity)
    _WORLD_KEY,
    build_global_outcome_probability_provider,
    build_simulator,
    convert_to_pytrees,
)
from pddl_planning.planner_core.solver import solve_from_files


CATEGORIES = ("action", "condition", "selector", "sequence", "decorator", "leaf_other")
WRAPPER_CATEGORIES = ("selector", "sequence", "decorator")


def _classify(behaviour: py_trees.behaviour.Behaviour) -> str:
    name = type(behaviour).__name__
    if isinstance(behaviour, py_trees.composites.Selector):
        return "selector"
    if isinstance(behaviour, py_trees.composites.Sequence):
        return "sequence"
    if isinstance(behaviour, py_trees.decorators.Decorator):
        return "decorator"
    if "Action" in name or name == "ExecuteAction":
        return "action"
    if "Condition" in name or name == "FluentCondition":
        return "condition"
    return "leaf_other"


class CategoryVisitCountVisitor(py_trees.visitors.VisitorBase):
    """Bins every visit during one root tick by node category."""

    def __init__(self):
        super().__init__(full=False)
        self.counts: Dict[str, int] = {c: 0 for c in CATEGORIES}

    def initialise(self) -> None:
        for c in CATEGORIES:
            self.counts[c] = 0

    def run(self, behaviour: py_trees.behaviour.Behaviour) -> None:
        self.counts[_classify(behaviour)] += 1


def _static_counts(root: py_trees.behaviour.Behaviour) -> Dict[str, int]:
    counts = {c: 0 for c in CATEGORIES}

    def walk(node):
        counts[_classify(node)] += 1
        for ch in getattr(node, "children", ()) or ():
            walk(ch)
        # decorators expose .decorated child via .children too in py_trees,
        # so we don't double-traverse.

    walk(root)
    return counts


def _simulate_with_categories(
    bt,
    domain_pddl: str,
    problem_pddl: str,
    *,
    n_trials: int,
    max_ticks: int,
    seed: int,
    outcome_probability_provider,
):
    import random

    rng = random.Random(seed)
    make_world, _, _, _, _ = build_simulator(domain_pddl, problem_pddl)
    pytree_root = convert_to_pytrees(bt.root, templates=bt.templates)
    tree = py_trees.trees.BehaviourTree(root=pytree_root)
    visitor = CategoryVisitCountVisitor()
    tree.add_visitor(visitor)
    tree.setup()

    writer = py_trees.blackboard.Client(name="CatVisitor")
    writer.register_key(key=_WORLD_KEY, access=py_trees.common.Access.WRITE)

    successes = 0
    timeouts = 0
    tick_totals: List[int] = []
    cat_totals: Dict[str, List[int]] = {c: [] for c in CATEGORIES}

    for _ in range(n_trials):
        world = make_world(rng=rng, outcome_probability_provider=outcome_probability_provider)
        writer.set(_WORLD_KEY, world)
        episode_ticks = 0
        episode_cat = {c: 0 for c in CATEGORIES}

        success = False
        for tick in range(1, max_ticks + 1):
            tree.tick()
            episode_ticks = tick
            for c in CATEGORIES:
                episode_cat[c] += visitor.counts[c]
            if world.goal_reached or world.check_goal():
                success = True
                break
            if pytree_root.status == py_trees.common.Status.FAILURE:
                break
        else:
            timeouts += 1

        tick_totals.append(episode_ticks)
        for c in CATEGORIES:
            cat_totals[c].append(episode_cat[c])
        if success:
            successes += 1

    return {
        "successes": successes,
        "timeouts": timeouts,
        "n_trials": n_trials,
        "avg_ticks": float(np.mean(tick_totals)) if tick_totals else 0.0,
        "avg_cat": {c: float(np.mean(cat_totals[c])) if cat_totals[c] else 0.0 for c in CATEGORIES},
    }


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


def _discover_instances(root: Path) -> List[Tuple[str, str, Path, Path]]:
    out = []
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        domain_file = None
        for cand in ("domain.pddl", "d.pddl"):
            p = d / cand
            if p.exists():
                domain_file = p
                break
        if domain_file is None:
            continue
        for problem_file in sorted(d.glob("*.pddl")):
            if problem_file.name == domain_file.name:
                continue
            if problem_file.name.startswith(("p", "problem")):
                out.append((d.name, problem_file.stem, domain_file, problem_file))
    return out


def plot_static(df: pd.DataFrame, out: Path) -> None:
    pivot = (
        df.assign(instance=df["domain"] + "/" + df["problem"])
        .drop_duplicates(["instance", "variant"])
        .melt(id_vars=["instance", "variant"], value_vars=[f"static_{c}" for c in CATEGORIES])
    )
    pivot["category"] = pivot["variable"].str.removeprefix("static_")

    instances = sorted(pivot["instance"].unique())
    variants = ["trivial", "hoisted"]
    fig, ax = plt.subplots(figsize=(11, 5.5))

    x = np.arange(len(instances))
    bar_w = 0.4
    palette = sns.color_palette("colorblind", len(CATEGORIES))
    colors = dict(zip(CATEGORIES, palette))

    for v_i, v in enumerate(variants):
        bottom = np.zeros(len(instances))
        for c in CATEGORIES:
            heights = []
            for inst in instances:
                row = pivot[(pivot["instance"] == inst) & (pivot["variant"] == v) & (pivot["category"] == c)]
                heights.append(float(row["value"].iloc[0]) if len(row) else 0.0)
            offset = (v_i - 0.5) * bar_w + bar_w / 2 - bar_w / 2
            ax.bar(
                x + (v_i - 0.5) * bar_w + bar_w / 2,
                heights,
                bar_w,
                bottom=bottom,
                color=colors[c],
                edgecolor="white",
                linewidth=0.4,
                label=f"{c}" if v_i == 0 else None,
            )
            bottom += np.array(heights)
        for i in range(len(instances)):
            ax.text(
                x[i] + (v_i - 0.5) * bar_w + bar_w / 2,
                bottom[i] + 1,
                v[0].upper(),
                ha="center",
                va="bottom",
                fontsize=8,
                alpha=0.7,
            )

    ax.set_xticks(x)
    ax.set_xticklabels(instances, rotation=30, ha="right")
    ax.set_ylabel("Static node count")
    ax.set_title("BT static node count by category (T = trivial, H = hoisted)")
    ax.grid(axis="y", linestyle="--", alpha=0.3)
    ax.legend(title="category", bbox_to_anchor=(1.02, 1), loc="upper left")
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


def plot_dynamic(df: pd.DataFrame, out: Path) -> None:
    profiles = sorted(df["profile"].unique())
    instances = sorted((df["domain"] + "/" + df["problem"]).unique())
    fig, axes = plt.subplots(len(profiles), 1, figsize=(12, 3.5 * len(profiles)), sharex=True)
    if len(profiles) == 1:
        axes = [axes]
    palette = sns.color_palette("colorblind", len(CATEGORIES))
    colors = dict(zip(CATEGORIES, palette))

    for ax, profile in zip(axes, profiles):
        sub = df[df["profile"] == profile].copy()
        sub["instance"] = sub["domain"] + "/" + sub["problem"]
        x = np.arange(len(instances))
        bar_w = 0.4
        for v_i, variant in enumerate(["trivial", "hoisted"]):
            bottom = np.zeros(len(instances))
            for c in CATEGORIES:
                col = f"dyn_avg_{c}"
                heights = []
                for inst in instances:
                    row = sub[(sub["instance"] == inst) & (sub["variant"] == variant)]
                    heights.append(float(row[col].iloc[0]) if len(row) else 0.0)
                ax.bar(
                    x + (v_i - 0.5) * bar_w + bar_w / 2,
                    heights,
                    bar_w,
                    bottom=bottom,
                    color=colors[c],
                    edgecolor="white",
                    linewidth=0.4,
                    label=c if v_i == 0 and ax is axes[0] else None,
                )
                bottom += np.array(heights)
            for i in range(len(instances)):
                ax.text(
                    x[i] + (v_i - 0.5) * bar_w + bar_w / 2,
                    bottom[i] + bottom[i] * 0.01 + 1,
                    variant[0].upper(),
                    ha="center",
                    va="bottom",
                    fontsize=8,
                    alpha=0.7,
                )

        ax.set_yscale("log")
        ax.set_xticks(x)
        ax.set_xticklabels(instances, rotation=30, ha="right")
        ax.set_ylabel("Avg per-episode visits (log)")
        ax.set_title(f"Profile = {profile}")
        ax.grid(axis="y", linestyle="--", alpha=0.3, which="both")

    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, title="category", loc="center right", bbox_to_anchor=(1.0, 0.5))
    fig.suptitle("Per-episode behaviour visits by node category (T = trivial, H = hoisted)", y=0.995)
    fig.tight_layout(rect=[0, 0, 0.9, 1])
    fig.savefig(out, dpi=150)
    plt.close(fig)


def plot_tradeoff(df: pd.DataFrame, out: Path) -> None:
    df = df.copy()
    df["instance"] = df["domain"] + "/" + df["problem"]
    pivot = df.pivot_table(
        index=["instance", "profile"],
        columns="variant",
        values=[f"dyn_avg_{c}" for c in CATEGORIES] + ["dyn_avg_ticks"],
    )
    rows = []
    for (instance, profile), row in pivot.iterrows():
        cond_delta = row[("dyn_avg_condition", "hoisted")] - row[("dyn_avg_condition", "trivial")]
        wrap_delta = sum(
            row[(f"dyn_avg_{c}", "hoisted")] - row[(f"dyn_avg_{c}", "trivial")] for c in WRAPPER_CATEGORIES
        )
        ticks_trivial = row[("dyn_avg_ticks", "trivial")]
        ticks_hoisted = row[("dyn_avg_ticks", "hoisted")]
        rows.append(
            {
                "instance": instance,
                "profile": profile,
                "cond_delta": cond_delta,
                "wrap_delta": wrap_delta,
                "ticks_trivial": ticks_trivial,
                "ticks_hoisted": ticks_hoisted,
            }
        )
    tr = pd.DataFrame(rows)
    if tr.empty:
        return

    fig, ax = plt.subplots(figsize=(8.5, 7))
    profiles = sorted(tr["profile"].unique())
    palette = sns.color_palette("colorblind", len(profiles))
    for color, profile in zip(palette, profiles):
        sub = tr[tr["profile"] == profile]
        ax.scatter(
            sub["cond_delta"],
            sub["wrap_delta"],
            label=profile,
            color=color,
            s=80,
            alpha=0.85,
            edgecolor="black",
            linewidth=0.4,
        )

    seen = set()
    for _, row in tr.iterrows():
        if row["instance"] in seen:
            continue
        seen.add(row["instance"])
        ax.annotate(
            row["instance"],
            (row["cond_delta"], row["wrap_delta"]),
            xytext=(4, 3),
            textcoords="offset points",
            fontsize=8,
            alpha=0.85,
        )

    lo = min(tr["cond_delta"].min(), -tr["wrap_delta"].max(), 0)
    hi = max(tr["cond_delta"].max(), -tr["wrap_delta"].min(), 0)
    span = max(abs(lo), abs(hi))
    line = np.linspace(-span, span, 2)
    ax.plot(line, -line, color="grey", linestyle=":", linewidth=0.8, label="break-even (y = -x)")
    ax.axhline(0, color="black", linewidth=0.4)
    ax.axvline(0, color="black", linewidth=0.4)

    ax.set_xlabel("Δ condition visits per episode  (hoisted - trivial)")
    ax.set_ylabel("Δ wrapper/decorator visits per episode  (hoisted - trivial)")
    ax.set_title(
        "Hoisting trade-off: condition checks saved vs wrapper checks added\n"
        "(below the dashed line: net node-tick win for hoisting)"
    )
    ax.legend(title="profile")
    ax.grid(linestyle="--", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--benchmarks-root", type=Path, default=_default_benchmark_root())
    p.add_argument("--profiles", type=str, default="uniform,mild_skew,strong_skew")
    p.add_argument("--trials", type=int, default=200)
    p.add_argument("--max-ticks", type=int, default=2000)
    p.add_argument("--seed", type=int, default=1337)
    p.add_argument("--timeout", type=float, default=120.0)
    p.add_argument("--backend", type=str, default="pr2", choices=["auto", "pr2", "up"])
    p.add_argument("--output-dir", type=Path, default=None)
    args = p.parse_args(argv)

    timestamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    out_dir = args.output_dir or (
        _Planner_ROOT / "output" / "bt_node_breakdown" / timestamp
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    profiles = [s.strip() for s in args.profiles.split(",") if s.strip()]
    instances = _discover_instances(args.benchmarks_root)
    if not instances:
        print("No instances")
        return 2

    rows: List[Dict[str, object]] = []

    for idx, (domain, problem, dpath, ppath) in enumerate(instances):
        print(f"[{idx+1}/{len(instances)}] {domain}/{problem}")
        try:
            sr = solve_from_files(dpath, ppath, backend=args.backend, timeout=args.timeout)
        except Exception as exc:
            print(f"  skip ({type(exc).__name__})")
            continue
        if not sr.is_policy or not sr.is_solved:
            print("  skip (no solved policy)")
            continue
        if not sr.is_strong_cyclic:
            print("  skip (non-strong-cyclic)")
            continue
        problem_obj = sr.metadata.get("problem") if isinstance(sr.metadata, dict) else None
        pol = sr.require_policy_result()
        bts = {
            "trivial": policy_to_bt_trivial(pol, problem=problem_obj),
            "hoisted": policy_to_bt(pol, problem=problem_obj),
        }
        domain_pddl = getattr(pol, "domain_pddl", "") or ""
        problem_pddl = getattr(pol, "problem_pddl", "") or ""
        if not domain_pddl or not problem_pddl:
            print("  skip (no pddl payload)")
            continue

        static_per_variant = {}
        for variant_name, bt in bts.items():
            pyroot = convert_to_pytrees(bt.root, templates=bt.templates)
            static_per_variant[variant_name] = _static_counts(pyroot)

        for prof_i, profile in enumerate(profiles):
            provider = build_global_outcome_probability_provider(profile)
            seed = int(args.seed + idx * 1000 + prof_i * 100000)
            for variant_name, bt in bts.items():
                stats = _simulate_with_categories(
                    bt,
                    domain_pddl,
                    problem_pddl,
                    n_trials=args.trials,
                    max_ticks=args.max_ticks,
                    seed=seed,
                    outcome_probability_provider=provider,
                )
                row: Dict[str, object] = {
                    "domain": domain,
                    "problem": problem,
                    "profile": profile,
                    "variant": variant_name,
                    "successes": stats["successes"],
                    "timeouts": stats["timeouts"],
                    "n_trials": stats["n_trials"],
                    "dyn_avg_ticks": stats["avg_ticks"],
                }
                for c in CATEGORIES:
                    row[f"static_{c}"] = static_per_variant[variant_name][c]
                    row[f"dyn_avg_{c}"] = stats["avg_cat"][c]
                rows.append(row)

    fields = [
        "domain", "problem", "profile", "variant",
        "successes", "timeouts", "n_trials", "dyn_avg_ticks",
    ] + [f"static_{c}" for c in CATEGORIES] + [f"dyn_avg_{c}" for c in CATEGORIES]
    csv_path = out_dir / "node_breakdown.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    df = pd.DataFrame(rows)
    if df.empty:
        print("no data")
        return 0

    plot_static(df, out_dir / "fig_node_breakdown_static.png")
    plot_dynamic(df, out_dir / "fig_node_breakdown_dynamic.png")
    plot_tradeoff(df, out_dir / "fig_condition_vs_wrapper_tradeoff.png")
    print(f"Outputs in {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
