"""
Policy -> trivial reactive Behavior Tree construction.

Step 4 builds the non-hoisted BT directly from the PR2 policy while preserving
rule order and FSAP semantics.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, List, Mapping, Optional, Tuple

from .execution_refs import resolve_action_execution_ref, resolve_predicate_execution_ref
from .literals import is_placeholder_literal
from .nodes import (
    ActionNode,
    BTNode,
    BehaviorTree,
    ConditionNode,
    FailureLeaf,
    Inverter,
    KeepRunningUntilFailure,
    ReactiveSelector,
    ReactiveSequence,
    Sequence,
    readable_action_id,
    sanitize_bt_id,
)


logger = logging.getLogger(__name__)


def _warn_placeholder(literal: object) -> None:
    logger.warning(
        "Dropping PR2 '<none of those>' placeholder literal %r in BT condition: "
        "expected expansion in unified_planning.engines.up_pr2.engine._parse_sas_mapping.",
        literal,
    )


@dataclass(frozen=True)
class _PolicyRuleView:
    condition: FrozenSet[str]
    action: str
    action_name: str
    action_args: Tuple[str, ...]


@dataclass(frozen=True)
class _FSAPView:
    condition: FrozenSet[str]
    action_name: str
    action_args: Tuple[str, ...]


_FSAPMap = Mapping[Tuple[str, Tuple[str, ...]], Tuple["_FSAPView", ...]]


def _value_is_false(value: object) -> bool:
    text = str(value).strip().lower()
    return text in {"false", "false()"}


def _condition_to_literals(raw_condition: object) -> FrozenSet[str]:
    def _filter(items):
        for raw in items:
            text = str(raw).strip()
            if not text:
                continue
            if is_placeholder_literal(text):
                _warn_placeholder(raw)
                continue
            yield text.lower()

    if isinstance(raw_condition, frozenset):
        return frozenset(_filter(raw_condition))
    if isinstance(raw_condition, set):
        return frozenset(_filter(raw_condition))
    if isinstance(raw_condition, dict):
        literals = set()
        for fluent, value in raw_condition.items():
            fluent_text = str(fluent).strip().lower()
            if not fluent_text:
                continue
            if is_placeholder_literal(fluent_text):
                _warn_placeholder(fluent)
                continue
            if _value_is_false(value):
                literals.add(f"not({fluent_text})")
            else:
                literals.add(fluent_text)
        return frozenset(literals)
    if raw_condition is None:
        return frozenset()
    text = str(raw_condition).strip().lower()
    if not text:
        return frozenset()
    if is_placeholder_literal(text):
        _warn_placeholder(raw_condition)
        return frozenset()
    return frozenset({text})


def _rule_action_text(rule: object) -> str:
    action = getattr(rule, "action", None)
    if action is not None:
        return str(action).strip()
    action_name = str(getattr(rule, "action_name", "")).strip()
    action_args = tuple(str(a).strip() for a in getattr(rule, "action_args", tuple()))
    return " ".join([action_name, *action_args]).strip()


def _normalize_policy_rules(policy_rules: List[object]) -> List[_PolicyRuleView]:
    normalized: List[_PolicyRuleView] = []
    for rule in policy_rules:
        raw_literals = getattr(rule, "raw_condition_literals", None)
        condition = _condition_to_literals(
            raw_literals if raw_literals else getattr(rule, "condition", frozenset())
        )
        action_name = str(getattr(rule, "action_name", "")).strip()
        action_args = tuple(str(a).strip() for a in getattr(rule, "action_args", tuple()))
        action = _rule_action_text(rule)
        if not action_name:
            action_name = action.split()[0] if action else ""
        if not action_args and action:
            tokens = action.split()
            if len(tokens) > 1:
                action_args = tuple(tokens[1:])
        normalized.append(
            _PolicyRuleView(
                condition=condition,
                action=action,
                action_name=action_name,
                action_args=action_args,
            )
        )
    return normalized


def _normalize_fsaps(fsaps: List[object]) -> List[_FSAPView]:
    normalized: List[_FSAPView] = []
    for fsap in fsaps:
        raw_literals = getattr(fsap, "raw_condition_literals", None)
        condition = _condition_to_literals(
            raw_literals if raw_literals else getattr(fsap, "condition", frozenset())
        )
        action_name = str(getattr(fsap, "action_name", "")).strip()
        action_args = tuple(str(a).strip() for a in getattr(fsap, "action_args", tuple()))
        if not action_name:
            continue
        normalized.append(
            _FSAPView(
                condition=condition,
                action_name=action_name,
                action_args=action_args,
            )
        )
    return normalized


def _build_fsap_map(fsaps: List[_FSAPView]) -> _FSAPMap:
    grouped: Dict[Tuple[str, Tuple[str, ...]], List[_FSAPView]] = defaultdict(list)
    for fsap in fsaps:
        grouped[(fsap.action_name, fsap.action_args)].append(fsap)
    return {key: tuple(value) for key, value in grouped.items()}


def _condition_nodes(
    fluents: FrozenSet[str],
    planner_metadata: Optional[Mapping[str, Any]] = None,
) -> List[BTNode]:
    return [_condition_node(f, planner_metadata=planner_metadata) for f in sorted(fluents)]


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


def _build_postcond_check(
    fluents: FrozenSet[str],
    name: str = "PostCond",
    planner_metadata: Optional[Mapping[str, Any]] = None,
) -> Optional[BTNode]:
    if not fluents:
        return None
    ordered = sorted(fluents)
    if len(ordered) == 1:
        return _condition_node(ordered[0], planner_metadata=planner_metadata)
    return ReactiveSequence(
        name,
        [_condition_node(f, planner_metadata=planner_metadata) for f in ordered],
    )


def _build_goal_branch(
    goal_rules: List[_PolicyRuleView],
    planner_metadata: Optional[Mapping[str, Any]] = None,
) -> Optional[BTNode]:
    if not goal_rules:
        return None

    all_conds: List[BTNode] = []
    for rule in goal_rules:
        cond = _build_postcond_check(
            frozenset(rule.condition),
            "GoalCond",
            planner_metadata=planner_metadata,
        )
        if cond is not None:
            all_conds.append(cond)

    if not all_conds:
        return None

    return all_conds[0] if len(all_conds) == 1 else ReactiveSelector("GoalCheck", all_conds)


def _flatten_goal_expr_literals(expr: object) -> List[str]:
    if expr is None:
        return []
    if hasattr(expr, "is_true") and expr.is_true():
        return []
    if hasattr(expr, "is_and") and expr.is_and():
        items: List[str] = []
        for arg in getattr(expr, "args", []):
            items.extend(_flatten_goal_expr_literals(arg))
        return items
    if hasattr(expr, "is_not") and expr.is_not():
        args = list(getattr(expr, "args", []))
        if len(args) == 1:
            return [f"not({str(args[0]).strip().lower()})"]
    return [str(expr).strip().lower()]


def _build_problem_goal_branch(
    problem: Optional[object],
    planner_metadata: Optional[Mapping[str, Any]] = None,
) -> Optional[BTNode]:
    if problem is None:
        return None

    goals = list(getattr(problem, "goals", []))
    goal_literals: List[str] = []
    for goal in goals:
        goal_literals.extend(_flatten_goal_expr_literals(goal))

    if not goal_literals:
        return None

    goal_conditions = frozenset(g for g in goal_literals if g)
    return _build_postcond_check(
        goal_conditions,
        "GoalCond",
        planner_metadata=planner_metadata,
    )


def _rule_action_key(rule: _PolicyRuleView) -> Tuple[str, Tuple[str, ...]]:
    return (rule.action_name, rule.action_args)


def _build_fsap_guard(
    fsap: _FSAPView,
    planner_metadata: Optional[Mapping[str, Any]] = None,
) -> Optional[BTNode]:
    literals = sorted(fsap.condition)
    if not literals:
        return None
    inner_children = [
        _condition_node(lit, planner_metadata=planner_metadata) for lit in literals
    ]
    if len(inner_children) == 1:
        inner: BTNode = inner_children[0]
    else:
        inner = ReactiveSequence(f"FSAPCond_{sanitize_bt_id(fsap.action_name)}", inner_children)
    return Inverter(inner)


def _build_uniform_rule_leaf(
    rule: _PolicyRuleView,
    planner_metadata: Optional[Mapping[str, Any]] = None,
    fsap_map: Optional[_FSAPMap] = None,
) -> BTNode:
    children: List[BTNode] = _condition_nodes(rule.condition, planner_metadata=planner_metadata)
    if fsap_map:
        for fsap in fsap_map.get(_rule_action_key(rule), ()):  # preserve PR2 order
            guard = _build_fsap_guard(fsap, planner_metadata=planner_metadata)
            if guard is not None:
                children.append(guard)
    children.append(
        ActionNode(
            rule.action,
            execution_ref=resolve_action_execution_ref(
                planner_metadata,
                rule.action_name or rule.action,
                rule.action_args,
            ),
        )
    )
    return Sequence(readable_action_id(rule.action), children, is_rule_leaf=True)


def _build_plain_rule_selector(
    rules: List[_PolicyRuleView],
    name: str,
    planner_metadata: Optional[Mapping[str, Any]] = None,
    fsap_map: Optional[_FSAPMap] = None,
) -> BTNode:
    branches = [
        _build_uniform_rule_leaf(
            rule, planner_metadata=planner_metadata, fsap_map=fsap_map
        )
        for rule in rules
    ]
    if len(branches) == 1:
        return branches[0]
    return ReactiveSelector(name, branches, is_rule_leaf=True)


def build_trivial_bt(
    result: object,
    problem: Optional[object] = None,
    planner_metadata: Optional[Mapping[str, Any]] = None,
) -> BehaviorTree:
    """Convert a policy plan into a non-hoisted trivial per-rule BT."""
    normalized_rules = _normalize_policy_rules(list(getattr(result, "policy", [])))
    raw_fsaps: List[object] = []
    try:
        raw_fsaps = list(getattr(result, "fsaps", []) or [])
    except TypeError:
        raw_fsaps = []
    fsap_map = _build_fsap_map(_normalize_fsaps(raw_fsaps))

    goal_rules = [r for r in normalized_rules if r.action_name == "goal"]
    action_rules = [r for r in normalized_rules if r.action_name != "goal"]

    branches: List[BTNode] = []
    goal_branch = _build_goal_branch(goal_rules, planner_metadata=planner_metadata)
    if goal_branch is None:
        problem_goal_check = _build_problem_goal_branch(problem, planner_metadata=planner_metadata)
        if problem_goal_check is not None:
            goal_branch = problem_goal_check
    if goal_branch is not None:
        branches.append(goal_branch)

    if not action_rules:
        if not branches:
            branches.append(FailureLeaf("EmptyPolicy"))
        root = ReactiveSelector("PolicyRoot", branches)
        return BehaviorTree(root)

    progression = _build_plain_rule_selector(
        action_rules,
        "Progression",
        planner_metadata=planner_metadata,
        fsap_map=fsap_map,
    )
    progression.is_rule_leaf = True
    branches.append(progression)

    if goal_branch is not None:
        looped_progression = KeepRunningUntilFailure(progression, name="PolicyLoop")
        root = ReactiveSelector("PolicyRoot", [goal_branch, looped_progression])
    else:
        root = branches[0] if len(branches) == 1 else ReactiveSelector("PolicyRoot", branches)

    return BehaviorTree(root)
