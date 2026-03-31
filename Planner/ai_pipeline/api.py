from __future__ import annotations

from typing import Any, Dict, List, Optional

from .merge import merge_sources as _merge_sources
from .models import AIPlanningPipelineResult, AIPlanningSource
from .parsing import parse_source as _parse_source
from .solve_export import (
    compile_trajectory_constraints as _compile_trajectory_constraints,
    export_problem_artifacts as _export_problem_artifacts,
    extract_plan_text as _extract_plan_text,
    solve_result_to_bt_xml as _solve_result_to_bt_xml,
    write_text_artifact as _write_text_artifact,
)
from .up_builder import (
    build_capabilities as _build_capabilities,
    build_up_problem as _build_up_problem,
)


def run_ai_planning_pipeline(
    sources: List[AIPlanningSource],
    timeout: Optional[float] = None,
    artifacts_dir: Optional[str] = None,
    allow_reduced_fallback: bool = True,
) -> AIPlanningPipelineResult:
    warnings: List[str] = []
    parsed_sources = [_parse_source(source) for source in sources]
    for parsed in parsed_sources:
        warnings.extend(parsed.warnings)

    merged = _merge_sources(parsed_sources, warnings)
    up_problem = _build_up_problem(merged, warnings, semantic_natural_transitions=True)
    artifacts = _export_problem_artifacts(up_problem, artifacts_dir, warnings)

    solve_result = _solve_up_problem(
        up_problem,
        merged,
        timeout,
        warnings,
        allow_reduced_fallback=allow_reduced_fallback,
    )
    bt_solve_result = solve_result

    bt_xml, conversion_warnings = _solve_result_to_bt_xml(solve_result)
    warnings.extend(conversion_warnings)

    if bt_xml:
        _write_text_artifact(artifacts, "behavior_tree_xml", "behavior_tree.xml", bt_xml, warnings)

    if solve_result.is_plan:
        plan_text = _extract_plan_text(solve_result)
        if plan_text:
            _write_text_artifact(artifacts, "deterministic_plan", "deterministic_plan.txt", plan_text, warnings)

    capabilities = _build_capabilities(merged)
    return AIPlanningPipelineResult(
        bt_xml=bt_xml,
        solve_result=solve_result,
        bt_solve_result=bt_solve_result,
        warnings=warnings,
        capabilities=capabilities,
        artifacts=artifacts,
    )


def _solve_up_problem(
    problem: Any,
    merged: Dict[str, Any],
    timeout: Optional[float],
    warnings: List[str],
    allow_reduced_fallback: bool,
) -> Any:
    from planner_core.solver import solve as solve_problem

    semantic_result = None
    semantic_error: Optional[Exception] = None

    solve_problem_input = problem
    map_back_action_instance = None
    if list(getattr(problem, "trajectory_constraints", [])):
        compiled_problem, map_back_action_instance = _compile_trajectory_constraints(problem, warnings)
        if compiled_problem is not None:
            warnings.append(
                "Trajectory constraints compiled before solving to match available planner capabilities."
            )
            solve_problem_input = compiled_problem

    try:
        semantic_result = solve_problem(solve_problem_input, backend="auto", timeout=timeout)
    except Exception as exc:
        semantic_error = exc

    if semantic_result is not None and map_back_action_instance is not None and getattr(semantic_result, "is_plan", False):
        try:
            up_result = semantic_result.require_plan_result()
            plan = getattr(up_result, "plan", None)
            if plan is not None:
                up_result.plan = plan.replace_action_instances(map_back_action_instance)
        except Exception as exc:
            warnings.append(f"Could not map compiled plan back to original actions: {exc}")

    if semantic_result is not None and getattr(semantic_result, "is_solved", False):
        return semantic_result

    if not allow_reduced_fallback:
        if semantic_result is not None:
            warnings.append("Reduced-model fallback disabled; returning unsolved semantic result.")
            return semantic_result
        if semantic_error is not None:
            raise RuntimeError(
                f"Semantic solve failed and reduced-model fallback is disabled: {semantic_error}"
            ) from semantic_error
        raise RuntimeError("Semantic solve returned no result and reduced-model fallback is disabled.")

    events_count = sum(1 for a in merged.get("actions", []) if str(a.get("action_kind") or "") == "Event")
    processes_count = sum(1 for a in merged.get("actions", []) if str(a.get("action_kind") or "") == "Process")
    constraints_count = len(merged.get("constraints_terms", []))

    reason = "semantic solve was unsolved"
    if semantic_error is not None:
        reason = f"semantic solve failed ({semantic_error})"

    warnings.append(f"Retrying solve with reduced model because {reason}.")
    warnings.append(
        "Reduced-model solve disregards unsupported/unsolved semantics: "
        f"Events={events_count}, Processes={processes_count}, Constraints={constraints_count}."
    )

    reduced_problem = _build_up_problem(
        merged,
        warnings,
        semantic_natural_transitions=False,
        drop_natural_transitions=True,
        include_trajectory_constraints=False,
    )
    reduced_result = solve_problem(reduced_problem, backend="auto", timeout=timeout)

    if getattr(reduced_result, "is_solved", False):
        warnings.append("Reduced-model solve succeeded; generated plan/BT excludes dropped semantics.")
        return reduced_result

    if semantic_result is not None:
        return semantic_result
    return reduced_result
