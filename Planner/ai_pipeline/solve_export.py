from __future__ import annotations

import datetime
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def compile_trajectory_constraints(
    problem: Any,
    warnings: List[str],
) -> Tuple[Optional[Any], Optional[Any]]:
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


def solve_result_to_bt_xml(solve_result: Any) -> Tuple[str, List[str]]:
    warnings: List[str] = []

    if not getattr(solve_result, "is_solved", False):
        warnings.append("Solve result is unsolved; BT generation skipped.")
        return "", warnings

    if getattr(solve_result, "is_policy", False):
        from bt_policy.api import bt_to_xml, policy_to_bt

        bt = policy_to_bt(solve_result.require_policy_result())
        return bt_to_xml(bt), warnings

    if getattr(solve_result, "is_plan", False):
        bt_xml = deterministic_plan_to_bt_xml(solve_result)
        if bt_xml:
            warnings.append("Generated linear BT from deterministic UP plan (PR2 conversion not used).")
            return bt_xml, warnings

        warnings.append("Deterministic plan solve succeeded but plan-to-BT conversion produced no XML.")
        return "", warnings

    warnings.append("Unknown solve result mode; BT generation skipped.")
    return "", warnings


def deterministic_plan_to_bt_xml(solve_result: Any) -> str:
    from bt_policy.nodes import ActionNode, BehaviorTree, ReactiveSequence, SuccessLeaf
    from bt_policy.xml_writer import bt_to_xml

    up_result = solve_result.require_plan_result()
    plan = getattr(up_result, "plan", None)
    if plan is None:
        return ""

    action_instances = list(getattr(plan, "actions", []))
    children: List[Any] = [action_instance_to_bt_action(ai) for ai in action_instances]
    children.append(SuccessLeaf())

    tree = BehaviorTree(ReactiveSequence("DeterministicPlan", children))
    return bt_to_xml(tree)


def action_instance_to_bt_action(action_instance: Any) -> Any:
    from bt_policy.nodes import ActionNode

    action = getattr(action_instance, "action", None)
    if action is None:
        return ActionNode(str(action_instance))

    action_name = str(getattr(action, "name", "") or str(action_instance))
    params: List[str] = []
    for parameter in getattr(action_instance, "actual_parameters", []):
        param_name = str(getattr(parameter, "name", "") or str(parameter))
        params.append(_safe_id(param_name))

    if params:
        return ActionNode(f"{action_name} {' '.join(params)}")
    return ActionNode(action_name)


def extract_plan_text(solve_result: Any) -> str:
    if not getattr(solve_result, "is_plan", False):
        return ""

    try:
        up_result = solve_result.require_plan_result()
    except Exception:
        return ""

    plan = getattr(up_result, "plan", None)
    if plan is None:
        return ""

    action_instances = list(getattr(plan, "actions", []))
    lines = [format_action_instance(ai) for ai in action_instances]
    return "\n".join(lines)


def format_action_instance(action_instance: Any) -> str:
    action = getattr(action_instance, "action", None)
    if action is None:
        return str(action_instance)

    action_name = str(getattr(action, "name", "") or str(action_instance))
    params: List[str] = []
    for parameter in getattr(action_instance, "actual_parameters", []):
        param_name = str(getattr(parameter, "name", "") or str(parameter))
        params.append(_safe_id(param_name))

    if params:
        return f"{action_name} {' '.join(params)}"
    return action_name


def export_problem_artifacts(problem: Any, artifacts_dir: Optional[str], warnings: List[str]) -> Dict[str, str]:
    out_dir = resolve_artifacts_dir(artifacts_dir)
    artifacts: Dict[str, str] = {"artifacts_dir": str(out_dir)}

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
    artifacts: Dict[str, str],
    key: str,
    filename: str,
    content: str,
    warnings: List[str],
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


def _safe_id(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9_]+", "_", value or "")
    if not sanitized:
        return "id"
    if sanitized[0].isdigit():
        sanitized = f"_{sanitized}"
    return sanitized
