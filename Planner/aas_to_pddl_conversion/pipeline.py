from __future__ import annotations

import datetime
from itertools import chain
from pathlib import Path
from typing import Any, Dict, Optional, Set

from .bop_ordering import compile_bop_ordering
from .merge import merge_sources
from .models import AIPlanningPipelineResult, AIPlanningSource
from .parsing import parse_source
from .up_builder import build_capabilities, build_up_problem

try:
    from ..pddl_planning.planner_core.solve_pipeline import solve_with_reduced_fallback
except ImportError:
    from pddl_planning.planner_core.solve_pipeline import solve_with_reduced_fallback


def run_ai_planning_pipeline(
    planning_sources: list[AIPlanningSource],
    *,
    planning_timeout_seconds: float,
    strict_semantic_solve: bool,
    bop_config: Optional[Dict[str, Any]] = None,
    artifacts_dir: Optional[str] = None,
) -> AIPlanningPipelineResult:
    """Run parse->merge->build->solve->export sequence for planning sources."""
    try:
        from ..bt_synthesis.api import extract_plan_text, solve_result_to_bt_xml
    except ImportError:
        from bt_synthesis.api import extract_plan_text, solve_result_to_bt_xml

    warnings: list[str] = []
    parsed_sources = [parse_source(source) for source in planning_sources]
    for parsed in parsed_sources:
        warnings.extend(parsed.warnings)

    merged = merge_sources(parsed_sources, warnings)
    compile_bop_ordering(merged, bop_config, warnings)
    up_problem = build_up_problem(merged, warnings, semantic_natural_transitions=True)
    artifacts = export_problem_artifacts(up_problem, artifacts_dir, warnings)

    solve_result = solve_with_reduced_fallback(
        up_problem,
        timeout=planning_timeout_seconds,
        warnings=warnings,
        allow_reduced_fallback=not strict_semantic_solve,
        build_reduced_problem=lambda: build_up_problem(
            merged,
            warnings,
            semantic_natural_transitions=False,
            drop_natural_transitions=True,
            include_trajectory_constraints=False,
        ),
        reduced_model_stats={
            "events": sum(1 for a in merged.get("actions", []) if str(a.get("action_kind") or "") == "Event"),
            "processes": sum(1 for a in merged.get("actions", []) if str(a.get("action_kind") or "") == "Process"),
            "constraints": len(merged.get("constraints_terms", [])),
        },
    )
    bt_solve_result = solve_result

    planner_metadata = {}
    solve_problem = getattr(solve_result, "metadata", {}).get("problem")
    if solve_problem is not None:
        planner_metadata = dict(getattr(solve_problem, "_planner_metadata", {}) or {})
    if not planner_metadata:
        planner_metadata = dict(getattr(up_problem, "_planner_metadata", {}) or {})
    if hasattr(solve_result, "metadata") and isinstance(getattr(solve_result, "metadata", None), dict):
        solve_result.metadata["planner_metadata"] = planner_metadata

    bt_xml, conversion_warnings = solve_result_to_bt_xml(solve_result)
    warnings.extend(conversion_warnings)

    if bt_xml:
        write_text_artifact(artifacts, "behavior_tree_xml", "behavior_tree.xml", bt_xml, warnings)

    if getattr(solve_result, "is_plan", False):
        plan_text = extract_plan_text(solve_result)
        if plan_text:
            write_text_artifact(artifacts, "deterministic_plan", "deterministic_plan.txt", plan_text, warnings)

    if getattr(solve_result, "is_policy", False):
        export_policy_visualization(solve_result, artifacts, warnings)

    capabilities = build_capabilities(merged)
    return AIPlanningPipelineResult(
        bt_xml=bt_xml,
        solve_result=solve_result,
        bt_solve_result=bt_solve_result,
        warnings=warnings,
        capabilities=capabilities,
        artifacts=artifacts,
        planner_metadata=planner_metadata,
    )


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


def resolve_artifacts_dir(artifacts_dir: Optional[str]) -> Path:
    if artifacts_dir:
        return Path(artifacts_dir)

    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return Path(__file__).resolve().parent.parent / "output" / "ai_planning_runs" / timestamp


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
    """Export a lifted causal graph as DOT, handling both deterministic and oneof effects."""
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

        def _process_effect(e: Any, action_name: str) -> None:
            _record_written(e.fluent, action_name)
            for fn in chain(fve.get(e.value), fve.get(e.condition)):
                _record_read(fn, action_name)

        for action in problem.actions:
            aname = action.name
            for p in action.preconditions:
                for fn in fve.get(p):
                    _record_read(fn, aname)
            for e in action.effects:
                _process_effect(e, aname)
            for oneof in getattr(action, "oneof_effects", []):
                for outcome in oneof.outcomes:
                    for e in outcome:
                        _process_effect(e, aname)

        all_fluents = sorted(set(fluents_read) | set(fluents_written))

        lines = ["digraph causal_graph {"]
        for f in all_fluents:
            lines.append(f'  "{f}";')
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


def export_policy_visualization(solve_result: Any, artifacts: dict[str, str], warnings: list[str]) -> None:
    """Export an interactive HTML policy state-transition graph."""
    out_dir_raw = artifacts.get("artifacts_dir")
    if not out_dir_raw:
        return

    try:
        try:
            from ..pddl_planning.visualization import create_force_graph_html
        except ImportError:
            from pddl_planning.visualization import create_force_graph_html

        domain_name = str(getattr(solve_result, "domain_name", "domain") or "domain")
        problem_name = str(getattr(solve_result, "problem_name", "problem") or "problem")

        html_path = Path(out_dir_raw) / "policy_graph.html"
        create_force_graph_html(solve_result, html_path, domain_name=domain_name, problem_name=problem_name)
        artifacts["policy_graph"] = str(html_path)
    except Exception as exc:
        warnings.append(f"Failed to export policy visualization: {exc}")
