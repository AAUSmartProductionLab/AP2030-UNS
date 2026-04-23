"""
Policy -> reactive Behavior Tree construction.

Converts a PR2 planner result into a compact reactive Behavior Tree using
condition hoisting and a deterministic tree-size heuristic.

Public API
----------
- ``policy_to_bt(result, problem=None)``
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, List, Mapping, Optional, Tuple

from .execution_refs import resolve_action_execution_ref, resolve_predicate_execution_ref

from .nodes import (
    BTNode,
    BehaviorTree,
    ActionNode,
    ConditionNode,
    FailureLeaf,
    Inverter,
    KeepRunningUntilFailure,
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


@dataclass(frozen=True)
class _FSAPView:
    """Forbidden state-action pair view (string-literal condition)."""

    condition: FrozenSet[str]
    action_name: str
    action_args: Tuple[str, ...]


_FSAPMap = Mapping[Tuple[str, Tuple[str, ...]], Tuple["_FSAPView", ...]]


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
    """Group FSAPs by (action_name, action_args) for fast lookup per rule."""
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

    goal_ok = all_conds[0] if len(all_conds) == 1 else ReactiveSelector("GoalCheck", all_conds)
    return ReactiveSequence("GoalBranch", [goal_ok, SuccessLeaf()])


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


def _rule_action_key(rule: _PolicyRuleView) -> Tuple[str, Tuple[str, ...]]:
    return (rule.action_name, rule.action_args)


def _build_fsap_guard(
    fsap: _FSAPView,
    planner_metadata: Optional[Mapping[str, Any]] = None,
) -> Optional[BTNode]:
    """Build a guard node that fails when the FSAP condition currently holds.

    The guard is ``Inverter(ReactiveSequence(fsap_literals))``: the inner
    sequence succeeds iff every FSAP literal holds; the inverter then
    fails, causing the surrounding action sequence to fail and the parent
    selector to try the next rule. An empty FSAP condition is unsupported
    (it would forbid the action unconditionally) and is skipped.
    """
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
        for fsap in fsap_map.get(_rule_action_key(rule), ()):  # preserve PR2 fsap order
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


def _longest_shared_run(
    rules: List[_PolicyRuleView], start: int
) -> Tuple[Optional[str], int]:
    """Find the longest contiguous run of rules starting at ``start`` that all
    share some common literal. Returns ``(literal, end_exclusive)`` or
    ``(None, start + 1)`` if no run of length >=2 with positive hoist gain
    exists.

    Hoist gain model: factoring a literal out of a run of length ``k`` saves
    ``k`` repeated condition checks at the cost of one extra Sequence wrapper
    plus one shared condition node, so net gain is ``k - 2`` (positive when
    ``k >= 3``). We still hoist at ``k == 2`` (zero gain) when it does not
    enlarge the tree, because the resulting structure is no worse and groups
    related rules visually. Adjust by requiring ``k >= 2`` here.
    """
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
        for rule in rules  # preserve PR2 file order
    ]
    if len(branches) == 1:
        return branches[0]
    return ReactiveSelector(name, branches, is_rule_leaf=True)


def _build_hoisted_rule_selector(
    rules: List[_PolicyRuleView],
    name: str,
    planner_metadata: Optional[Mapping[str, Any]] = None,
    fsap_map: Optional[_FSAPMap] = None,
) -> BTNode:
    """Order-preserving condition hoisting.

    Walks ``rules`` left-to-right (PR2 file order). At each position we look
    for the longest contiguous run of following rules that all share some
    literal. If found, that run is factored under a single condition gate
    and recursively hoisted; otherwise the current rule is emitted verbatim.
    Crucially, a hoist never reorders rules across a non-matching neighbor,
    so the resulting reactive selector preserves PR2's first-match semantics.
    """
    if not rules:
        return FailureLeaf("NoRule")
    if len(rules) == 1:
        return _build_uniform_rule_leaf(
            rules[0], planner_metadata=planner_metadata, fsap_map=fsap_map
        )

    branches: List[BTNode] = []
    i = 0
    while i < len(rules):
        literal, end = _longest_shared_run(rules, i)
        if literal is None or (end - i) < 2:
            branches.append(
                _build_uniform_rule_leaf(
                    rules[i], planner_metadata=planner_metadata, fsap_map=fsap_map
                )
            )
            i += 1
            continue

        run_rules = [
            _PolicyRuleView(
                condition=frozenset(c for c in r.condition if c != literal),
                action=r.action,
                action_name=r.action_name,
                action_args=r.action_args,
            )
            for r in rules[i:end]
        ]
        lit_id = sanitize_bt_id(literal)
        inner_name = f"{name}_with_{lit_id}"
        inner = _build_hoisted_rule_selector(
            run_rules,
            inner_name,
            planner_metadata=planner_metadata,
            fsap_map=fsap_map,
        )
        hoisted_branch = Sequence(
            f"When_{lit_id}",
            [_condition_node(literal, planner_metadata=planner_metadata), inner],
            is_rule_leaf=True,
        )
        branches.append(hoisted_branch)
        i = end

    if len(branches) == 1:
        return branches[0]
    return ReactiveSelector(name, branches, is_rule_leaf=True)


def _flatten_linear_condition_sequences(node: BTNode) -> BTNode:
    """Flatten chains like Sequence(cond, Sequence(cond2, ...)).

    Hoisting can produce deep linear stacks of gate sequences. This pass
    collapses contiguous condition-only gate layers into one Sequence,
    stopping at the next non-Sequence branching point.
    """
    if isinstance(node, (ReactiveSelector, ReactiveSequence, Sequence)):
        node.children = [_flatten_linear_condition_sequences(c) for c in node.children]

    if isinstance(node, KeepRunningUntilFailure):
        node.child = _flatten_linear_condition_sequences(node.child)
        return node

    if not isinstance(node, Sequence):
        return node

    def _is_condition_gate(candidate: BTNode) -> bool:
        if isinstance(candidate, ConditionNode):
            return True
        if isinstance(candidate, Inverter) and isinstance(candidate.child, ConditionNode):
            return True
        return False

    while (
        len(node.children) == 2
        and _is_condition_gate(node.children[0])
        and isinstance(node.children[1], Sequence)
    ):
        nested = node.children[1]
        node.children = [node.children[0], *nested.children]
        node.is_rule_leaf = node.is_rule_leaf or nested.is_rule_leaf

    return node


def policy_to_bt(
    result: object,
    problem: Optional[object] = None,
    planner_metadata: Optional[Mapping[str, Any]] = None,
    hoist_conditions: bool = True,
) -> BehaviorTree:
    """Convert a policy plan into a reactive Behavior Tree.

    The synthesised tree faithfully reproduces PR2's first-match
    semantics: rules are emitted in their original ``policy.out`` order,
    and FSAP forbidden state-action pairs are turned into guards that
    cause the corresponding action sequence to fail (so the parent
    selector falls through to the next rule), exactly as PR2's
    ``next_action`` validator does.

    When ``hoist_conditions`` is ``True`` (default), conditions shared by
    *contiguous runs* of policy rules are factored into a common gate.
    Hoists never reorder rules across a non-matching neighbor, so the
    PR2 first-match contract is preserved. With ``hoist_conditions`` set
    to ``False`` the result is a trivial per-rule reactive selector that
    still respects PR2 file order and FSAP guards.
    """
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
            goal_branch = ReactiveSequence("GoalBranch", [problem_goal_check, SuccessLeaf()])
    if goal_branch is not None:
        branches.append(goal_branch)

    if not action_rules:
        if not branches:
            branches.append(FailureLeaf("EmptyPolicy"))
        root = ReactiveSelector("PolicyRoot", branches)
        return BehaviorTree(root)

    if hoist_conditions:
        all_conditions_common, reduced_rules = _hoist_common(action_rules)
        progression = _build_hoisted_rule_selector(
            reduced_rules,
            "Progression",
            planner_metadata=planner_metadata,
            fsap_map=fsap_map,
        )
        progression = _flatten_linear_condition_sequences(progression)

        if all_conditions_common:
            gate_children = _condition_nodes(
                all_conditions_common,
                planner_metadata=planner_metadata,
            )
            gate_children.append(progression)
            progression = Sequence("PolicyRules", gate_children, is_rule_leaf=True)
    else:
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

    bt = BehaviorTree(root)
    parameterize_subtrees(bt)
    bt.root = deduplicate_subtrees(bt.root)
    return bt


def policy_to_bt_trivial(
    result: object,
    problem: Optional[object] = None,
    planner_metadata: Optional[Mapping[str, Any]] = None,
) -> BehaviorTree:
    """Convert a policy plan into a non-hoisted trivial per-rule BT."""
    return policy_to_bt(
        result,
        problem=problem,
        planner_metadata=planner_metadata,
        hoist_conditions=False,
    )
