from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

from .solver import solve as solve_problem


def compile_trajectory_constraints(
    problem: Any,
    warnings: List[str],
) -> Tuple[Optional[Any], Optional[Any]]:
    """Compile trajectory constraints into planner-compatible constraints."""
    try:
        from unified_planning.engines.compilers.trajectory_constraints_remover import (
            TrajectoryConstraintsRemover,
        )

        compiler = TrajectoryConstraintsRemover()
        compilation_result = compiler.compile(problem)
        return compilation_result.problem, compilation_result.map_back_action_instance
    except Exception as exc:
        warnings.append(f"Failed to compile trajectory constraints: {exc}")
        return None, None


def solve_with_reduced_fallback(
    problem: Any,
    *,
    timeout: Optional[float],
    warnings: List[str],
    allow_reduced_fallback: bool,
    build_reduced_problem: Callable[[], Any],
    reduced_model_stats: Optional[Dict[str, int]] = None,
) -> Any:
    """Solve a UP problem and optionally retry with a reduced model.

    This keeps solve strategy and fallback policy colocated with planner-core
    solving logic instead of generation modules.
    """
    semantic_result = None
    semantic_error: Optional[Exception] = None

    solve_problem_input = problem
    map_back_action_instance = None
    if list(getattr(problem, "trajectory_constraints", [])):
        compiled_problem, map_back_action_instance = compile_trajectory_constraints(problem, warnings)
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

    stats = reduced_model_stats or {}
    events_count = int(stats.get("events", 0))
    processes_count = int(stats.get("processes", 0))
    constraints_count = int(stats.get("constraints", 0))

    reason = "semantic solve was unsolved"
    if semantic_error is not None:
        reason = f"semantic solve failed ({semantic_error})"

    warnings.append(f"Retrying solve with reduced model because {reason}.")
    warnings.append(
        "Reduced-model solve disregards unsupported/unsolved semantics: "
        f"Events={events_count}, Processes={processes_count}, Constraints={constraints_count}."
    )

    reduced_problem = build_reduced_problem()
    reduced_result = solve_problem(reduced_problem, backend="auto", timeout=timeout)

    if getattr(reduced_result, "is_solved", False):
        warnings.append("Reduced-model solve succeeded; generated plan/BT excludes dropped semantics.")
        return reduced_result

    if semantic_result is not None:
        return semantic_result
    return reduced_result
