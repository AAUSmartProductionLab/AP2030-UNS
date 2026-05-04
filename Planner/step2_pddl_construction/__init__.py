"""Step 2: UP PDDL problem and domain construction."""

from __future__ import annotations

import datetime
from itertools import chain
from pathlib import Path
from typing import Any, Dict, Optional, Set

from .bop_ordering import compile_bop_ordering
from .merge import merge_sources
from .models import ActionRef, AIPlanningPipelineResult, PlanningCapability, PredicateRef
from .up_builder import build_capabilities, build_up_problem


def resolve_artifacts_dir(artifacts_dir: Optional[str]) -> Path:
    if artifacts_dir:
        return Path(artifacts_dir)

    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return Path(__file__).resolve().parent.parent / "output" / "ai_planning_runs" / timestamp


def export_problem_artifacts(problem: Any, artifacts_dir: Optional[str], warnings: list[str]) -> dict[str, str]:
    out_dir = resolve_artifacts_dir(artifacts_dir)
    artifacts: dict[str, str] = {"artifacts_dir": str(out_dir)}

    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        warnings.append(f"Failed to create artifacts directory '{out_dir}': {exc}")
        return artifacts

    try:
        from unified_planning.io import PDDLWriter

        writer = PDDLWriter(problem)
        domain_text = writer.get_domain()
        problem_text = writer.get_problem()

        domain_path = out_dir / "domain.pddl"
        problem_path = out_dir / "problem.pddl"
        domain_path.write_text(domain_text)
        problem_path.write_text(problem_text)

        artifacts["domain_pddl"] = str(domain_path)
        artifacts["problem_pddl"] = str(problem_path)
    except Exception as exc:
        warnings.append(f"Failed to export PDDL artifacts: {exc}")

    return artifacts


def write_text_artifact(
    artifacts: dict[str, str],
    key: str,
    filename: str,
    content: str,
    warnings: list[str],
) -> str:
    out_dir_raw = artifacts.get("artifacts_dir")
    if not out_dir_raw:
        return ""

    out_dir = Path(out_dir_raw)

    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = out_dir / filename
        output_path.write_text(content)
        artifacts[key] = str(output_path)
        return str(output_path)
    except Exception as exc:
        warnings.append(f"Failed to write artifact '{filename}': {exc}")
        return ""


def export_causal_graph(problem: Any, artifacts: dict[str, str], warnings: list[str]) -> None:
    """Export a lifted causal graph as DOT, handling deterministic and oneof effects."""
    out_dir_raw = artifacts.get("artifacts_dir")
    if not out_dir_raw:
        return

    try:
        fve = problem.environment.free_vars_extractor

        fluents_read: Dict[str, Set[str]] = {}
        fluents_written: Dict[str, Set[str]] = {}

        def _record_read(fluent_node: Any, action_name: str) -> None:
            fluents_read.setdefault(fluent_node.fluent().name, set()).add(action_name)

        def _record_written(fluent_node: Any, action_name: str) -> None:
            fluents_written.setdefault(fluent_node.fluent().name, set()).add(action_name)

        def _process_effect(effect: Any, action_name: str) -> None:
            _record_written(effect.fluent, action_name)
            for fluent_node in chain(fve.get(effect.value), fve.get(effect.condition)):
                _record_read(fluent_node, action_name)

        for action in problem.actions:
            action_name = action.name
            for precondition in action.preconditions:
                for fluent_node in fve.get(precondition):
                    _record_read(fluent_node, action_name)
            for effect in action.effects:
                _process_effect(effect, action_name)
            for oneof in getattr(action, "oneof_effects", []):
                for outcome in oneof.outcomes:
                    for effect in outcome:
                        _process_effect(effect, action_name)

        all_fluents = sorted(set(fluents_read) | set(fluents_written))

        lines = ["digraph causal_graph {"]
        for fluent in all_fluents:
            lines.append(f'  "{fluent}";')
        for left in all_fluents:
            left_actions = fluents_read.get(left, set()) | fluents_written.get(left, set())
            for right in sorted(fluents_written):
                if left != right:
                    shared = left_actions & fluents_written[right]
                    if shared:
                        label = ",".join(sorted(shared))
                        lines.append(f'  "{left}" -> "{right}" [label="{label}"];')
        lines.append("}")

        dot_path = Path(out_dir_raw) / "causal_graph.dot"
        dot_path.write_text("\n".join(lines))
        artifacts["causal_graph"] = str(dot_path)
    except Exception as exc:
        warnings.append(f"Failed to export causal graph: {exc}")


__all__ = [
    "ActionRef",
    "AIPlanningPipelineResult",
    "PlanningCapability",
    "PredicateRef",
    "build_capabilities",
    "build_up_problem",
    "compile_bop_ordering",
    "merge_sources",
    "resolve_artifacts_dir",
    "export_problem_artifacts",
    "write_text_artifact",
    "export_causal_graph",
]
