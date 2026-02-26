"""
Behavior Tree optimization passes: parameterization and deduplication.

- **Parameterization** — groups of structurally similar action subtrees
  are collapsed into a single template with ``{argN}`` placeholders and
  replaced by ``SubTreeRef`` nodes.
- **Deduplication** — bottom-up structural signature comparison replaces
  behaviourally equivalent subtrees with shared references.
"""

from __future__ import annotations

import copy
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

from bt_nodes import (
    ActionNode,
    BTNode,
    BehaviorTree,
    ConditionNode,
    FailureLeaf,
    ForbiddenActionNode,
    Inverter,
    ReactiveSelector,
    ReactiveSequence,
    SubTreeRef,
    SuccessLeaf,
    to_camel_case,
)


# ===================================================================
#  Parameterized subtree extraction
# ===================================================================


def _find_action_node(node: BTNode) -> Optional[ActionNode]:
    """Find the ActionNode in a subtree (DFS)."""
    if isinstance(node, ActionNode):
        return node
    if isinstance(node, (ReactiveSequence, ReactiveSelector)):
        for child in node.children:
            found = _find_action_node(child)
            if found is not None:
                return found
    if isinstance(node, Inverter):
        return _find_action_node(node.child)
    return None


def _compute_template_sig(node: BTNode, arg_values: List[str]) -> str:
    """Structural signature with arg values replaced by positional placeholders."""
    replacements = sorted(
        [(val, f"{{${i}}}") for i, val in enumerate(arg_values)],
        key=lambda x: -len(x[0]),
    )

    def _r(s: str) -> str:
        for val, ph in replacements:
            s = s.replace(val, ph)
        return s

    if isinstance(node, ConditionNode):
        return f"C:{_r(node.fluent)}"
    if isinstance(node, ActionNode):
        return f"A:{_r(node.action_name)}"
    if isinstance(node, ForbiddenActionNode):
        return f"X:{_r(node.forbidden_action)}"
    if isinstance(node, SuccessLeaf):
        return "S"
    if isinstance(node, FailureLeaf):
        return f"F:{node.name}"
    if isinstance(node, Inverter):
        return f"I({_compute_template_sig(node.child, arg_values)})"
    if isinstance(node, ReactiveSequence):
        inner = ",".join(_compute_template_sig(c, arg_values) for c in node.children)
        return f"Seq({inner})"
    if isinstance(node, ReactiveSelector):
        inner = ",".join(_compute_template_sig(c, arg_values) for c in node.children)
        return f"Sel({inner})"
    return f"?:{node.name}"


def _replace_in_tree(
    node: BTNode,
    arg_values: List[str],
    param_names: List[str],
) -> None:
    """In-place replacement of concrete arg values with ``{param}`` placeholders."""
    replacements = sorted(
        list(zip(arg_values, param_names)),
        key=lambda x: -len(x[0]),
    )

    def _r(s: str) -> str:
        for val, name in replacements:
            s = s.replace(val, f"{{{name}}}")
        return s

    if isinstance(node, ConditionNode):
        node.fluent = _r(node.fluent)
        node.name = _r(node.name)
    elif isinstance(node, ActionNode):
        node.action_name = _r(node.action_name)
        node.name = _r(node.name)
    elif isinstance(node, ForbiddenActionNode):
        node.forbidden_action = _r(node.forbidden_action)
        node.name = _r(node.name)
    elif isinstance(node, ReactiveSequence):
        node.name = _r(node.name)
        for child in node.children:
            _replace_in_tree(child, arg_values, param_names)
    elif isinstance(node, ReactiveSelector):
        node.name = _r(node.name)
        for child in node.children:
            _replace_in_tree(child, arg_values, param_names)
    elif isinstance(node, Inverter):
        _replace_in_tree(node.child, arg_values, param_names)


def _create_template_tree(
    node: BTNode,
    arg_values: List[str],
    param_names: List[str],
) -> BTNode:
    """Deep-copy *node* and replace concrete arg values with placeholders."""
    template = copy.deepcopy(node)
    _replace_in_tree(template, arg_values, param_names)
    return template


def parameterize_subtrees(bt: BehaviorTree) -> None:
    """Replace groups of structurally similar action subtrees with parameterized refs.

    For each group of 2+ subtrees sharing the same template signature:
    1. Creates a parameterized template with ``{argN}`` placeholders.
    2. Registers the template on *bt.templates*.
    3. Replaces each instance with a ``SubTreeRef`` node.
    """
    LeafEntry = Tuple[BTNode, Optional[BTNode], Optional[int]]
    leaf_entries: List[LeafEntry] = []

    def _collect(
        node: BTNode,
        parent: Optional[BTNode] = None,
        child_idx: Optional[int] = None,
    ):
        if node.is_rule_leaf:
            leaf_entries.append((node, parent, child_idx))
        if isinstance(node, (ReactiveSequence, ReactiveSelector)):
            for i, child in enumerate(node.children):
                _collect(child, node, i)
        elif isinstance(node, Inverter):
            _collect(node.child, node, 0)

    _collect(bt.root)

    ActionEntry = Tuple[BTNode, Optional[BTNode], Optional[int], str, List[str]]
    leaf_action_info: List[ActionEntry] = []
    for node, parent, cidx in leaf_entries:
        action_node = _find_action_node(node)
        if action_node is None:
            continue
        parts = action_node.action_name.split()
        if len(parts) < 2:
            continue
        action_type = parts[0]
        action_args = parts[1:]
        leaf_action_info.append((node, parent, cidx, action_type, action_args))

    by_type: Dict[str, List[ActionEntry]] = defaultdict(list)
    for entry in leaf_action_info:
        by_type[entry[3]].append(entry)

    used_ids: Set[str] = set()

    for action_type, members in by_type.items():
        sig_groups: Dict[str, List[ActionEntry]] = defaultdict(list)
        for entry in members:
            sig = _compute_template_sig(entry[0], entry[4])
            sig_groups[sig].append(entry)

        for sig, group in sig_groups.items():
            if len(group) < 2:
                continue

            tid = to_camel_case(action_type)
            suffix = 2
            while tid in used_ids:
                tid = f"{to_camel_case(action_type)}_v{suffix}"
                suffix += 1
            used_ids.add(tid)

            first_node, _, _, _, first_args = group[0]
            n_args = len(first_args)
            param_names = [f"arg{i}" for i in range(n_args)]
            template_tree = _create_template_tree(first_node, first_args, param_names)
            bt.templates[tid] = (template_tree, param_names)

            for node, parent, cidx, _atype, args in group:
                params = dict(zip(param_names, args))
                ref = SubTreeRef(tid, params)
                if parent is not None:
                    if isinstance(parent, (ReactiveSequence, ReactiveSelector)):
                        parent.children[cidx] = ref
                    elif isinstance(parent, Inverter):
                        parent.child = ref


# ===================================================================
#  Structural subtree deduplication
# ===================================================================


def structural_signature(node: BTNode) -> str:
    """Canonical string signature for a subtree.

    Two subtrees with identical signatures are behaviourally equivalent.
    """
    if isinstance(node, ConditionNode):
        return f"C:{node.fluent}"
    if isinstance(node, ActionNode):
        return f"A:{node.action_name}"
    if isinstance(node, ForbiddenActionNode):
        return f"X:{node.forbidden_action}"
    if isinstance(node, SuccessLeaf):
        return "S"
    if isinstance(node, FailureLeaf):
        return f"F:{node.name}"
    if isinstance(node, SubTreeRef):
        params_str = ",".join(f"{k}={v}" for k, v in sorted(node.params.items()))
        return f"SubRef:{node.template_id}({params_str})"
    if isinstance(node, Inverter):
        return f"I({structural_signature(node.child)})"
    if isinstance(node, ReactiveSequence):
        inner = ",".join(structural_signature(c) for c in node.children)
        return f"Seq({inner})"
    if isinstance(node, ReactiveSelector):
        inner = ",".join(structural_signature(c) for c in node.children)
        return f"Sel({inner})"
    return f"?:{node.name}"


def deduplicate_subtrees(root: BTNode) -> BTNode:
    """Bottom-up deduplication by structural signature.

    Replaces children with a previously-seen identical subtree (same
    object), so the XML serialiser emits shared SubTree definitions.
    """
    sig_to_node: Dict[str, BTNode] = {}

    def _dedup(node: BTNode) -> BTNode:
        if isinstance(node, ReactiveSequence):
            node.children = [_dedup(c) for c in node.children]
        elif isinstance(node, ReactiveSelector):
            node.children = [_dedup(c) for c in node.children]
        elif isinstance(node, Inverter):
            node.child = _dedup(node.child)

        sig = structural_signature(node)
        canonical = sig_to_node.get(sig)
        if canonical is not None:
            return canonical
        sig_to_node[sig] = node
        return node

    return _dedup(root)
