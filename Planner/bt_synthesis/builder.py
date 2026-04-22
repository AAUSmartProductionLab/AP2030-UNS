"""
Policy -> reactive Behavior Tree construction.

Converts a PR2 planner result into a compact reactive Behavior Tree using
condition hoisting and a deterministic tree-size heuristic.

Public API
----------
- ``policy_to_bt(result, problem=None)``
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import FrozenSet, List, Optional, Tuple

from .nodes import (
    BTNode,
    BehaviorTree,
    ActionNode,
    ConditionNode,
    FailureLeaf,
    Sequence,
    ReactiveSelector,
    ReactiveSequence,
    SuccessLeaf,
    readable_action_id,
    sanitize_bt_id,
)
from .optimizer import deduplicate_subtrees, parameterize_subtrees


@dataclass(frozen=True)
class _PolicyRuleView:
    condition: FrozenSet[str]
    action: str
    action_name: str
    action_args: Tuple[str, ...]


def _value_is_false(value: object) -> bool:
    text = str(value).strip().lower()
    return text in {"false", "false()"}


def _condition_to_literals(raw_condition: object) -> FrozenSet[str]:
    if isinstance(raw_condition, frozenset):
        return frozenset(str(l).strip().lower() for l in raw_condition if str(l).strip())
    if isinstance(raw_condition, set):
        return frozenset(str(l).strip().lower() for l in raw_condition if str(l).strip())
    if isinstance(raw_condition, dict):
        literals = set()
        for fluent, value in raw_condition.items():
            fluent_text = str(fluent).strip().lower()
            if not fluent_text:
                continue
            if _value_is_false(value):
                literals.add(f"not({fluent_text})")
            else:
                literals.add(fluent_text)
        return frozenset(literals)
    if raw_condition is None:
        return frozenset()
    return frozenset({str(raw_condition).strip().lower()})


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


def _condition_nodes(fluents: FrozenSet[str]) -> List[ConditionNode]:
    return [ConditionNode(f) for f in sorted(fluents)]


def _build_postcond_check(
    fluents: FrozenSet[str],
    name: str = "PostCond",
) -> Optional[BTNode]:
    if not fluents:
        return None
    ordered = sorted(fluents)
    if len(ordered) == 1:
        return ConditionNode(ordered[0])
    return ReactiveSequence(name, [ConditionNode(f) for f in ordered])


def _build_goal_branch(goal_rules: List[_PolicyRuleView]) -> Optional[BTNode]:
    if not goal_rules:
        return None

    all_conds: List[BTNode] = []
    for rule in goal_rules:
        cond = _build_postcond_check(frozenset(rule.condition), "GoalCond")
        if cond is not None:
            all_conds.append(cond)

    if not all_conds:
        return None

    goal_ok = all_conds[0] if len(all_conds) == 1 else ReactiveSelector("GoalCheck", all_conds)
    return ReactiveSequence("GoalBranch", [goal_ok, SuccessLeaf()])


def _hoist_common(
    rules: List[_PolicyRuleView],
) -> Tuple[FrozenSet[str], List[_PolicyRuleView]]:
    if not rules:
        return frozenset(), []

    common = set(rules[0].condition)
    for r in rules[1:]:
        common &= r.condition
    if not common:
        return frozenset(), rules

    common_fs = frozenset(common)
    reduced = [
        _PolicyRuleView(
            condition=frozenset(r.condition - common_fs),
            action=r.action,
            action_name=r.action_name,
            action_args=r.action_args,
        )
        for r in rules
    ]
    return common_fs, reduced


def _rule_sort_key(rule: _PolicyRuleView) -> Tuple[str, str, Tuple[str, ...]]:
    return (
        rule.action,
        rule.action_name,
        tuple(sorted(rule.condition)),
    )


def _build_uniform_rule_leaf(rule: _PolicyRuleView) -> BTNode:
    children: List[BTNode] = _condition_nodes(rule.condition)
    children.append(ActionNode(rule.action))
    return Sequence(readable_action_id(rule.action), children, is_rule_leaf=True)


def _select_hoist_literal(rules: List[_PolicyRuleView]) -> Optional[str]:
    frequency: Counter[str] = Counter()
    for rule in rules:
        frequency.update(rule.condition)

    best_literal: Optional[str] = None
    best_score: Optional[Tuple[int, int, str]] = None
    for literal, count in frequency.items():
        if count < 2:
            continue
        # Hoisting gain model: remove repeated checks, pay one sequence wrapper.
        gain = count - 2
        score = (gain, count, literal)
        if best_score is None or score > best_score:
            best_score = score
            best_literal = literal

    if best_score is None or best_score[0] < 0:
        return None
    return best_literal


def _build_plain_rule_selector(rules: List[_PolicyRuleView], name: str) -> BTNode:
    ordered = sorted(rules, key=_rule_sort_key)
    branches = [_build_uniform_rule_leaf(rule) for rule in ordered]
    if len(branches) == 1:
        return branches[0]
    return ReactiveSelector(name, branches, is_rule_leaf=True)


def _build_hoisted_rule_selector(rules: List[_PolicyRuleView], name: str) -> BTNode:
    if not rules:
        return FailureLeaf("NoRule")
    if len(rules) == 1:
        return _build_uniform_rule_leaf(rules[0])

    literal = _select_hoist_literal(rules)
    if literal is None:
        return _build_plain_rule_selector(rules, name)

    with_literal: List[_PolicyRuleView] = []
    without_literal: List[_PolicyRuleView] = []
    for rule in rules:
        if literal in rule.condition:
            with_literal.append(
                _PolicyRuleView(
                    condition=frozenset(c for c in rule.condition if c != literal),
                    action=rule.action,
                    action_name=rule.action_name,
                    action_args=rule.action_args,
                )
            )
        else:
            without_literal.append(rule)

    if not with_literal:
        return _build_plain_rule_selector(rules, name)

    lit_id = sanitize_bt_id(literal)
    hoisted_inner = _build_hoisted_rule_selector(with_literal, f"{name}_with_{lit_id}")
    hoisted_branch = Sequence(
        f"When_{lit_id}",
        [ConditionNode(literal), hoisted_inner],
        is_rule_leaf=True,
    )

    if not without_literal:
        return hoisted_branch

    other_branch = _build_hoisted_rule_selector(
        without_literal,
        f"{name}_else_{lit_id}",
    )
    return ReactiveSelector(name, [hoisted_branch, other_branch], is_rule_leaf=True)


def policy_to_bt(result: object, problem: Optional[object] = None) -> BehaviorTree:
    """Convert a policy plan into a condition-hoisted reactive BT.

    FSAPs are intentionally ignored in BT synthesis.
    The *problem* argument is accepted for API compatibility.
    """
    _ = problem
    normalized_rules = _normalize_policy_rules(list(getattr(result, "policy", [])))

    goal_rules = [r for r in normalized_rules if r.action_name == "goal"]
    action_rules = [r for r in normalized_rules if r.action_name != "goal"]

    branches: List[BTNode] = []
    goal_branch = _build_goal_branch(goal_rules)
    if goal_branch is not None:
        branches.append(goal_branch)

    if not action_rules:
        if not branches:
            branches.append(FailureLeaf("EmptyPolicy"))
        root = ReactiveSelector("PolicyRoot", branches)
        return BehaviorTree(root)

    all_conditions_common, reduced_rules = _hoist_common(action_rules)
    progression = _build_hoisted_rule_selector(reduced_rules, "Progression")

    if all_conditions_common:
        gate_children = _condition_nodes(all_conditions_common)
        gate_children.append(progression)
        progression = Sequence("PolicyRules", gate_children, is_rule_leaf=True)

    progression.is_rule_leaf = True
    branches.append(progression)

    root = ReactiveSelector("PolicyRoot", branches)

    bt = BehaviorTree(root)
    parameterize_subtrees(bt)
    bt.root = deduplicate_subtrees(bt.root)
    return bt
