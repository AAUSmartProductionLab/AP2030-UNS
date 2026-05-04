from __future__ import annotations

from typing import Any, Mapping, Optional

from .execution_refs import resolve_action_execution_ref, resolve_predicate_execution_ref
from ..step2_pddl_construction.utils import safe_id

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

    from ..step6_bt_serialization.xml_writer import bt_to_xml
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

    cond_nodes = [_condition_node(g, planner_metadata=planner_metadata) for g in goal_literals]
    if len(cond_nodes) == 1:
        return cond_nodes[0]
    return ReactiveSequence("GoalCond", cond_nodes)


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
