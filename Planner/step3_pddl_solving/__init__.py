"""Step 3: PDDL solving with PR2-UP integration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .solve_pipeline import solve_with_reduced_fallback
from .solve_result import SolveResult
from .solver import BackendName, solve, solve_from_files
from .visualization import create_force_graph_html


def export_policy_visualization(solve_result: Any, artifacts: dict[str, str], warnings: list[str]) -> None:
    """Export an interactive HTML policy state-transition graph."""
    out_dir_raw = artifacts.get("artifacts_dir")
    if not out_dir_raw:
        return

    try:
        domain_name = str(getattr(solve_result, "domain_name", "domain") or "domain")
        problem_name = str(getattr(solve_result, "problem_name", "problem") or "problem")

        html_path = Path(out_dir_raw) / "policy_graph.html"
        create_force_graph_html(
            solve_result,
            html_path,
            domain_name=domain_name,
            problem_name=problem_name,
        )
        artifacts["policy_graph"] = str(html_path)
    except Exception as exc:
        warnings.append(f"Failed to export policy visualization: {exc}")


__all__ = [
    "BackendName",
    "SolveResult",
    "solve",
    "solve_from_files",
    "solve_with_reduced_fallback",
    "create_force_graph_html",
    "export_policy_visualization",
]
