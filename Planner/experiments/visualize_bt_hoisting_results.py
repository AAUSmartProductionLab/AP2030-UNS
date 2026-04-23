#!/usr/bin/env python3
"""Visualize hoisted-vs-trivial BT equivalence experiment results.

Reads ``summary.csv`` and ``episodes.csv`` produced by
``run_bt_hoisting_equivalence.py`` and writes a set of PNG figures
addressing two questions:

  1. Are the strong / strong-cyclic policy guarantees preserved by both
     synthesised BT variants?
  2. How big is the node-tick reduction of hoisted vs trivial?

Figures
-------
- ``fig_success_rates.png``        — grouped bars: success rate per
  (domain, problem, profile) for trivial and hoisted, with planner
  classification overlay.
- ``fig_timeout_rates.png``        — counterpart for timeout rate.
- ``fig_node_tick_reduction.png``  — bars of relative node-tick
  reduction (trivial vs hoisted) per (domain, problem, profile) on
  successful episodes.
- ``fig_node_ticks_box.png``       — paired boxplot per domain of
  per-episode node ticks for trivial vs hoisted on successful
  episodes.
- ``fig_size_vs_speedup.png``      — scatter: static node-count
  reduction vs runtime node-tick reduction.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import List

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns


def _instance_label(row: pd.Series) -> str:
    return f"{row['domain']}/{row['problem']}"


def _profile_grid(df: pd.DataFrame) -> List[str]:
    return sorted(df["profile"].unique().tolist())


def plot_success_rates(summary: pd.DataFrame, out: Path) -> None:
    profiles = _profile_grid(summary)
    fig, axes = plt.subplots(
        len(profiles), 1, figsize=(11, 3.0 * len(profiles)), sharex=True
    )
    if len(profiles) == 1:
        axes = [axes]

    for ax, profile in zip(axes, profiles):
        sub = summary[summary["profile"] == profile].copy()
        sub["instance"] = sub.apply(_instance_label, axis=1)
        sub = sub.sort_values("instance")

        x = np.arange(len(sub))
        width = 0.38
        ax.bar(x - width / 2, sub["trivial_success_rate"], width, label="trivial", color="#4C78A8")
        ax.bar(x + width / 2, sub["hoisted_success_rate"], width, label="hoisted", color="#F58518")

        for i, expected in enumerate(sub["expected_solved"].tolist()):
            if expected:
                ax.axhline(1.0, color="#54A24B", linestyle=":", alpha=0.4, linewidth=0.8)
                ax.scatter(i, 1.02, marker="*", color="#54A24B", s=40, clip_on=False)

        ax.set_ylim(0, 1.08)
        ax.set_ylabel("Success rate")
        ax.set_title(f"Profile = {profile}")
        ax.set_xticks(x)
        ax.set_xticklabels(sub["instance"], rotation=30, ha="right")
        ax.grid(axis="y", linestyle="--", alpha=0.3)
        ax.legend(loc="lower right")

    fig.suptitle("Strong-cyclic guarantee preservation: success rate by variant", y=0.995)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


def plot_timeout_rates(summary: pd.DataFrame, out: Path) -> None:
    profiles = _profile_grid(summary)
    fig, axes = plt.subplots(
        len(profiles), 1, figsize=(11, 3.0 * len(profiles)), sharex=True
    )
    if len(profiles) == 1:
        axes = [axes]

    for ax, profile in zip(axes, profiles):
        sub = summary[summary["profile"] == profile].copy()
        sub["instance"] = sub.apply(_instance_label, axis=1)
        sub = sub.sort_values("instance")
        x = np.arange(len(sub))
        width = 0.38
        ax.bar(x - width / 2, sub["trivial_timeout_rate"], width, label="trivial", color="#4C78A8")
        ax.bar(x + width / 2, sub["hoisted_timeout_rate"], width, label="hoisted", color="#F58518")
        ax.set_ylim(0, max(0.05, sub[["trivial_timeout_rate", "hoisted_timeout_rate"]].values.max() * 1.1))
        ax.set_ylabel("Timeout rate")
        ax.set_title(f"Profile = {profile}")
        ax.set_xticks(x)
        ax.set_xticklabels(sub["instance"], rotation=30, ha="right")
        ax.grid(axis="y", linestyle="--", alpha=0.3)
        ax.legend(loc="upper right")

    fig.suptitle("Timeout rate by variant", y=0.995)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


def plot_node_tick_reduction(summary: pd.DataFrame, out: Path) -> None:
    df = summary.copy()
    df["instance"] = df.apply(_instance_label, axis=1)
    df = df[df["trivial_avg_node_ticks_success"] > 0]
    df["node_tick_reduction_ratio"] = (
        (df["trivial_avg_node_ticks_success"] - df["hoisted_avg_node_ticks_success"])
        / df["trivial_avg_node_ticks_success"]
    )

    profiles = _profile_grid(df)
    fig, ax = plt.subplots(figsize=(11, 5.5))
    instances = sorted(df["instance"].unique().tolist())
    x = np.arange(len(instances))
    width = 0.8 / max(1, len(profiles))
    palette = sns.color_palette("colorblind", len(profiles))

    for i, profile in enumerate(profiles):
        sub = df[df["profile"] == profile].set_index("instance").reindex(instances)
        offsets = x + (i - (len(profiles) - 1) / 2) * width
        ax.bar(
            offsets,
            sub["node_tick_reduction_ratio"].fillna(0).values,
            width,
            label=profile,
            color=palette[i],
        )

    ax.axhline(0, color="black", linewidth=0.6)
    ax.set_ylabel("Node-tick reduction ratio  (1 - hoisted/trivial)")
    ax.set_xticks(x)
    ax.set_xticklabels(instances, rotation=30, ha="right")
    ax.grid(axis="y", linestyle="--", alpha=0.3)
    ax.legend(title="profile")
    ax.set_title("Hoisting impact on per-episode node ticks (success episodes only)")
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


def plot_node_ticks_box(episodes: pd.DataFrame, out: Path) -> None:
    df = episodes[episodes["success"] == 1].copy()
    if df.empty:
        return
    df["instance"] = df["domain"] + "/" + df["problem"]

    profiles = _profile_grid(df)
    fig, axes = plt.subplots(
        len(profiles), 1, figsize=(11, 3.5 * len(profiles)), sharex=True
    )
    if len(profiles) == 1:
        axes = [axes]

    for ax, profile in zip(axes, profiles):
        sub = df[df["profile"] == profile]
        sns.boxplot(
            data=sub,
            x="instance",
            y="node_ticks",
            hue="variant",
            hue_order=["trivial", "hoisted"],
            palette={"trivial": "#4C78A8", "hoisted": "#F58518"},
            ax=ax,
            fliersize=1.5,
            linewidth=0.8,
        )
        ax.set_yscale("log")
        ax.set_ylabel("Node ticks per successful episode (log)")
        ax.set_title(f"Profile = {profile}")
        ax.tick_params(axis="x", rotation=30)
        for label in ax.get_xticklabels():
            label.set_horizontalalignment("right")
        ax.grid(axis="y", linestyle="--", alpha=0.3, which="both")
        ax.legend(title="variant", loc="upper right")

    fig.suptitle("Per-episode node-tick distribution (successful trials)", y=0.995)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


def plot_size_vs_speedup(summary: pd.DataFrame, out: Path) -> None:
    df = summary.copy()
    df = df[(df["trivial_nodes"] > 0) & (df["trivial_avg_node_ticks_success"] > 0)]
    if df.empty:
        return
    df["size_reduction"] = (df["trivial_nodes"] - df["hoisted_nodes"]) / df["trivial_nodes"]
    df["tick_reduction"] = (
        (df["trivial_avg_node_ticks_success"] - df["hoisted_avg_node_ticks_success"])
        / df["trivial_avg_node_ticks_success"]
    )
    df["instance"] = df.apply(_instance_label, axis=1)

    fig, ax = plt.subplots(figsize=(8.5, 6.5))
    profiles = _profile_grid(df)
    palette = sns.color_palette("colorblind", len(profiles))
    for color, profile in zip(palette, profiles):
        sub = df[df["profile"] == profile]
        ax.scatter(
            sub["size_reduction"],
            sub["tick_reduction"],
            label=profile,
            color=color,
            s=70,
            alpha=0.85,
            edgecolor="black",
            linewidth=0.4,
        )

    seen = set()
    for _, row in df.iterrows():
        key = row["instance"]
        if key in seen:
            continue
        seen.add(key)
        ax.annotate(
            key,
            (row["size_reduction"], row["tick_reduction"]),
            xytext=(4, 3),
            textcoords="offset points",
            fontsize=8,
            alpha=0.8,
        )

    lo = min(df["size_reduction"].min(), df["tick_reduction"].min(), 0)
    hi = max(df["size_reduction"].max(), df["tick_reduction"].max(), 0)
    ax.plot([lo, hi], [lo, hi], color="grey", linestyle=":", linewidth=0.8, label="y = x")
    ax.axhline(0, color="black", linewidth=0.4)
    ax.axvline(0, color="black", linewidth=0.4)
    ax.set_xlabel("Static node-count reduction  (1 - hoisted/trivial)")
    ax.set_ylabel("Runtime node-tick reduction  (1 - hoisted/trivial)")
    ax.set_title("Compile-time vs runtime impact of hoisting")
    ax.legend(title="profile")
    ax.grid(linestyle="--", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results_dir", type=Path)
    parser.add_argument("--out-dir", type=Path, default=None)
    args = parser.parse_args(argv)

    summary_path = args.results_dir / "summary.csv"
    episodes_path = args.results_dir / "episodes.csv"
    if not summary_path.exists():
        print(f"Missing: {summary_path}")
        return 2

    out_dir = args.out_dir or (args.results_dir / "figures")
    out_dir.mkdir(parents=True, exist_ok=True)

    summary = pd.read_csv(summary_path)
    plot_success_rates(summary, out_dir / "fig_success_rates.png")
    plot_timeout_rates(summary, out_dir / "fig_timeout_rates.png")
    plot_node_tick_reduction(summary, out_dir / "fig_node_tick_reduction.png")
    plot_size_vs_speedup(summary, out_dir / "fig_size_vs_speedup.png")

    if episodes_path.exists():
        episodes = pd.read_csv(episodes_path)
        plot_node_ticks_box(episodes, out_dir / "fig_node_ticks_box.png")

    print(f"Figures written to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
