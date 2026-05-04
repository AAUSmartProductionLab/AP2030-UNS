"""Condition-hoisting pass for trivial policy BTs."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Dict, FrozenSet, List, Optional, Tuple

from ..step4_policy_to_bt.nodes import (
    BTNode,
    BehaviorTree,
    ConditionNode,
    Inverter,
    KeepRunningUntilFailure,
    ReactiveSelector,
    Sequence,
    sanitize_bt_id,
)


@dataclass(frozen=True)
class _RuleBranch:
    name: str
    condition: FrozenSet[str]
    remainder: Tuple[BTNode, ...]


def _is_condition_gate(node: BTNode) -> bool:
    if isinstance(node, ConditionNode):
        return True
    if isinstance(node, Inverter) and isinstance(node.child, ConditionNode):
        return True
    return False


def _condition_literal(node: BTNode) -> Optional[str]:
    if isinstance(node, ConditionNode):
        return str(node.fluent).strip()
    if isinstance(node, Inverter) and isinstance(node.child, ConditionNode):
        base = str(node.child.fluent).strip()
        return f"not({base})" if base else None
    return None


def _clone_condition_node(
    literal: str,
    templates: Dict[str, BTNode],
) -> BTNode:
    node = templates.get(literal)
    if node is not None:
        return copy.deepcopy(node)

    text = str(literal or "").strip()
    lowered = text.lower()
    if lowered.startswith("not(") and text.endswith(")"):
        base = text[4:-1].strip()
        return Inverter(ConditionNode(base))
    return ConditionNode(text)


def _extract_rule_branches(
    progression: BTNode,
) -> Tuple[Optional[List[_RuleBranch]], Dict[str, BTNode]]:
    if isinstance(progression, ReactiveSelector):
        branches = list(progression.children)
    else:
        branches = [progression]

    views: List[_RuleBranch] = []
    literal_templates: Dict[str, BTNode] = {}

    for branch in branches:
        if not isinstance(branch, Sequence):
            return None, {}

        children = list(branch.children)
        idx = 0
        literals: List[str] = []
        while idx < len(children) and _is_condition_gate(children[idx]):
            lit = _condition_literal(children[idx])
            if lit:
                literals.append(lit)
                literal_templates.setdefault(lit, copy.deepcopy(children[idx]))
            idx += 1

        remainder = tuple(copy.deepcopy(children[idx:]))
        views.append(
            _RuleBranch(
                name=str(branch.name or "Rule"),
                condition=frozenset(literals),
                remainder=remainder,
            )
        )

    return views, literal_templates


def _hoist_common(rules: List[_RuleBranch]) -> Tuple[FrozenSet[str], List[_RuleBranch]]:
    if not rules:
        return frozenset(), []

    common = set(rules[0].condition)
    for rule in rules[1:]:
        common &= rule.condition
    if not common:
        return frozenset(), rules

    common_fs = frozenset(common)
    reduced = [
        _RuleBranch(
            name=rule.name,
            condition=frozenset(rule.condition - common_fs),
            remainder=rule.remainder,
        )
        for rule in rules
    ]
    return common_fs, reduced


def _longest_shared_run(
    rules: List[_RuleBranch],
    start: int,
) -> Tuple[Optional[str], int]:
    if start >= len(rules):
        return None, start + 1

    candidates = set(rules[start].condition)
    if not candidates:
        return None, start + 1

    best_literal: Optional[str] = None
    best_end = start + 1
    for literal in sorted(candidates):
        end = start + 1
        while end < len(rules) and literal in rules[end].condition:
            end += 1
        run = end - start
        if run < 2:
            continue
        if best_literal is None or run > (best_end - start):
            best_literal = literal
            best_end = end

    if best_literal is None:
        return None, start + 1
    return best_literal, best_end


def _build_uniform_rule_leaf(
    rule: _RuleBranch,
    templates: Dict[str, BTNode],
) -> BTNode:
    cond_nodes = [_clone_condition_node(lit, templates) for lit in sorted(rule.condition)]
    remainder = [copy.deepcopy(node) for node in rule.remainder]
    return Sequence(
        rule.name,
        cond_nodes + remainder,
        is_rule_leaf=True,
    )


def _build_hoisted_selector(
    rules: List[_RuleBranch],
    name: str,
    templates: Dict[str, BTNode],
) -> BTNode:
    if not rules:
        return Sequence("NoRule", [], is_rule_leaf=True)
    if len(rules) == 1:
        return _build_uniform_rule_leaf(rules[0], templates)

    branches: List[BTNode] = []
    i = 0
    while i < len(rules):
        literal, end = _longest_shared_run(rules, i)
        if literal is None or (end - i) < 2:
            branches.append(_build_uniform_rule_leaf(rules[i], templates))
            i += 1
            continue

        run_rules = [
            _RuleBranch(
                name=rule.name,
                condition=frozenset(c for c in rule.condition if c != literal),
                remainder=rule.remainder,
            )
            for rule in rules[i:end]
        ]

        inner = _build_hoisted_selector(
            run_rules,
            f"{name}_with_{sanitize_bt_id(literal)}",
            templates,
        )
        hoisted_branch = Sequence(
            f"When_{sanitize_bt_id(literal)}",
            [_clone_condition_node(literal, templates), inner],
            is_rule_leaf=True,
        )
        branches.append(hoisted_branch)
        i = end

    if len(branches) == 1:
        return branches[0]
    return ReactiveSelector(name, branches, is_rule_leaf=True)


def _flatten_linear_condition_sequences(node: BTNode) -> BTNode:
    if isinstance(node, ReactiveSelector):
        node.children = [_flatten_linear_condition_sequences(c) for c in node.children]

    if isinstance(node, KeepRunningUntilFailure):
        node.child = _flatten_linear_condition_sequences(node.child)
        return node

    if not isinstance(node, Sequence):
        return node

    node.children = [_flatten_linear_condition_sequences(c) for c in node.children]

    while (
        len(node.children) == 2
        and _is_condition_gate(node.children[0])
        and isinstance(node.children[1], Sequence)
    ):
        nested = node.children[1]
        node.children = [node.children[0], *nested.children]
        node.is_rule_leaf = node.is_rule_leaf or nested.is_rule_leaf

    return node


def _hoist_progression(progression: BTNode) -> BTNode:
    rules, templates = _extract_rule_branches(progression)
    if not rules or len(rules) < 2:
        return progression

    all_common, reduced = _hoist_common(rules)
    hoisted = _build_hoisted_selector(reduced, "Progression", templates)
    hoisted = _flatten_linear_condition_sequences(hoisted)

    if all_common:
        gate_children = [_clone_condition_node(lit, templates) for lit in sorted(all_common)]
        gate_children.append(hoisted)
        hoisted = Sequence("PolicyRules", gate_children, is_rule_leaf=True)

    hoisted.is_rule_leaf = True
    return hoisted


def hoist_conditions(trivial_bt: BehaviorTree) -> BehaviorTree:
    """Return a copy of *trivial_bt* with progression conditions hoisted."""
    bt = copy.deepcopy(trivial_bt)
    root = bt.root

    if isinstance(root, ReactiveSelector) and root.name == "PolicyRoot":
        if len(root.children) >= 2 and isinstance(root.children[1], KeepRunningUntilFailure):
            root.children[1].child = _hoist_progression(root.children[1].child)
            return bt
        if root.children:
            root.children[-1] = _hoist_progression(root.children[-1])
            return bt

    bt.root = _hoist_progression(root)
    return bt
