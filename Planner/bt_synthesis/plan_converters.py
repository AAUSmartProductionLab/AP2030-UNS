from __future__ import annotations

from typing import Any, Mapping, Optional

from .execution_refs import resolve_action_execution_ref, resolve_predicate_execution_ref

from .nodes import (
    ActionNode,
    BTNode,
    BehaviorTree,
    ConditionNode,
    Inverter,
    ReactiveSelector,
    ReactiveSequence,
    SuccessLeaf,
)
from .xml_writer import bt_to_xml


def solve_result_to_bt_xml(solve_result: Any) -> tuple[str, list[str]]:
    warnings: list[str] = []
    metadata = getattr(solve_result, "metadata", {})
    planner_metadata = metadata.get("planner_metadata", {}) if isinstance(metadata, dict) else {}

    if not getattr(solve_result, "is_solved", False):
        warnings.append("Solve result is unsolved; BT generation skipped.")
        return "", warnings

    if getattr(solve_result, "is_policy", False):
        from .api import policy_to_bt

        bt = policy_to_bt(
            solve_result.require_policy_result(),
            problem=getattr(solve_result, "metadata", {}).get("problem"),
            planner_metadata=planner_metadata,
        )
        return bt_to_xml(bt, planner_metadata=planner_metadata), warnings

    if getattr(solve_result, "is_plan", False):
        bt_xml = deterministic_plan_to_bt_xml(solve_result, planner_metadata=planner_metadata)
        if bt_xml:
            warnings.append("Generated reactive BT from deterministic UP plan.")
            return bt_xml, warnings

        warnings.append("Deterministic plan solve succeeded but plan-to-BT conversion produced no XML.")
        return "", warnings

    warnings.append("Unknown solve result mode; BT generation skipped.")
    return "", warnings


def deterministic_plan_to_bt_xml(
    solve_result: Any,
    planner_metadata: Optional[Mapping[str, Any]] = None,
) -> str:
    up_result = solve_result.require_plan_result()
    plan = getattr(up_result, "plan", None)
    if plan is None:
        return ""

    problem = getattr(solve_result, "metadata", {}).get("problem")

    action_instances = list(getattr(plan, "actions", []))
    progression_children: list[Any] = []
    for ai in action_instances:
        preconditions = _extract_precondition_literals(ai)
        action_node = action_instance_to_bt_action(ai, planner_metadata=planner_metadata)
        if preconditions:
            progression_children.append(
                ReactiveSequence(
                    f"Step_{action_node.action_name.replace(' ', '_')}",
                    [_condition_node(p, planner_metadata=planner_metadata) for p in preconditions]
                    + [action_node],
                )
            )
        else:
            progression_children.append(action_node)
    progression_children.append(SuccessLeaf())

    progression = BehaviorTree(ReactiveSequence("DeterministicPlan", progression_children))
    goal_branch = _build_problem_goal_branch(problem, planner_metadata=planner_metadata)
    if goal_branch is not None:
        progression.root = ReactiveSelector("PlanRoot", [goal_branch, progression.root])

    return bt_to_xml(progression, planner_metadata=planner_metadata)


def _flatten_bool_expr_literals(expr: Any) -> list[str]:
    if expr is None:
        return []
    if hasattr(expr, "is_true") and expr.is_true():
        return []
    if hasattr(expr, "is_and") and expr.is_and():
        items: list[str] = []
        for arg in getattr(expr, "args", []):
            items.extend(_flatten_bool_expr_literals(arg))
        return items
    if hasattr(expr, "is_not") and expr.is_not():
        args = list(getattr(expr, "args", []))
        if len(args) == 1:
            inner = args[0]
            return [f"not({inner})"]
        return [str(expr)]
    return [str(expr)]


def _extract_precondition_literals(action_instance: Any) -> list[str]:
    action = getattr(action_instance, "action", None)
    if action is None:
        return []

    parameters = list(getattr(action, "parameters", []))
    actual_parameters = list(getattr(action_instance, "actual_parameters", []))
    substitutions = {
        parameter: actual
        for parameter, actual in zip(parameters, actual_parameters)
    }

    literals: list[str] = []
    for precondition in list(getattr(action, "preconditions", [])):
        try:
            grounded = precondition.substitute(substitutions)
        except Exception:
            grounded = precondition
        literals.extend(_flatten_bool_expr_literals(grounded))
    return literals


def _build_problem_goal_branch(
    problem: Any,
    planner_metadata: Optional[Mapping[str, Any]] = None,
) -> Any:
    if problem is None:
        return None

    goals = list(getattr(problem, "goals", []))
    goal_literals: list[str] = []
    for goal in goals:
        goal_literals.extend(_flatten_bool_expr_literals(goal))
    if not goal_literals:
        return None

    return ReactiveSequence(
        "GoalBranch",
        [_condition_node(g, planner_metadata=planner_metadata) for g in goal_literals]
        + [SuccessLeaf()],
    )


def _split_negated_literal(literal: str) -> tuple[str, bool]:
    text = str(literal or "").strip()
    lowered = text.lower()
    if lowered.startswith("not(") and text.endswith(")"):
        return text[4:-1].strip(), True
    return text, False


def _condition_node(
    literal: str,
    planner_metadata: Optional[Mapping[str, Any]] = None,
) -> BTNode:
    base_literal, negated = _split_negated_literal(literal)
    leaf = ConditionNode(
        base_literal,
        execution_ref=resolve_predicate_execution_ref(planner_metadata, base_literal),
    )
    if negated:
        return Inverter(leaf)
    return leaf


def action_instance_to_bt_action(
    action_instance: Any,
    planner_metadata: Optional[Mapping[str, Any]] = None,
) -> ActionNode:
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

    execution_ref = resolve_action_execution_ref(planner_metadata, action_name, params)

    if params:
        return ActionNode(f"{action_name} {' '.join(params)}", execution_ref=execution_ref)
    return ActionNode(action_name, execution_ref=execution_ref)


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
