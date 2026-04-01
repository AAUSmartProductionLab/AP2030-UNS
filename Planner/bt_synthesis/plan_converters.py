from __future__ import annotations

from typing import Any

from .nodes import ActionNode, BehaviorTree, ReactiveSequence, SuccessLeaf
from .xml_writer import bt_to_xml


def solve_result_to_bt_xml(solve_result: Any) -> tuple[str, list[str]]:
    warnings: list[str] = []

    if not getattr(solve_result, "is_solved", False):
        warnings.append("Solve result is unsolved; BT generation skipped.")
        return "", warnings

    if getattr(solve_result, "is_policy", False):
        from .api import policy_to_bt

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
    up_result = solve_result.require_plan_result()
    plan = getattr(up_result, "plan", None)
    if plan is None:
        return ""

    action_instances = list(getattr(plan, "actions", []))
    children: list[Any] = [action_instance_to_bt_action(ai) for ai in action_instances]
    children.append(SuccessLeaf())

    tree = BehaviorTree(ReactiveSequence("DeterministicPlan", children))
    return bt_to_xml(tree)


def action_instance_to_bt_action(action_instance: Any) -> ActionNode:
    try:
        from ..aas_to_pddl_conversion.utils import safe_id
    except ImportError:
        from aas_to_pddl_conversion.utils import safe_id

    action = getattr(action_instance, "action", None)
    if action is None:
        return ActionNode(str(action_instance))

    action_name = str(getattr(action, "name", "") or str(action_instance))
    params: list[str] = []
    for parameter in getattr(action_instance, "actual_parameters", []):
        param_name = str(getattr(parameter, "name", "") or str(parameter))
        params.append(safe_id(param_name))

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
    try:
        from ..aas_to_pddl_conversion.utils import safe_id
    except ImportError:
        from aas_to_pddl_conversion.utils import safe_id

    action = getattr(action_instance, "action", None)
    if action is None:
        return str(action_instance)

    action_name = str(getattr(action, "name", "") or str(action_instance))
    params: list[str] = []
    for parameter in getattr(action_instance, "actual_parameters", []):
        param_name = str(getattr(parameter, "name", "") or str(parameter))
        params.append(safe_id(param_name))

    if params:
        return f"{action_name} {' '.join(params)}"
    return action_name
