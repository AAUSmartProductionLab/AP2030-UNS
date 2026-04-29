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

from .nodes import (
    ActionNode,
    BTNode,
    BehaviorTree,
    ConditionNode,
    FailureLeaf,
    ForbiddenActionNode,
    Inverter,
    KeepRunningUntilFailure,
    Sequence,
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
    if isinstance(node, (ReactiveSequence, ReactiveSelector, Sequence)):
        for child in node.children:
            found = _find_action_node(child)
            if found is not None:
                return found
    if isinstance(node, (Inverter, KeepRunningUntilFailure)):
        return _find_action_node(node.child)
    return None


def _count_action_leaves(node: BTNode) -> int:
    """Count the number of ``ActionNode`` leaves reachable from *node*."""
    if isinstance(node, ActionNode):
        return 1
    if isinstance(node, (ReactiveSequence, ReactiveSelector, Sequence)):
        return sum(_count_action_leaves(c) for c in node.children)
    if isinstance(node, (Inverter, KeepRunningUntilFailure)):
        return _count_action_leaves(node.child)
    return 0


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
    if isinstance(node, KeepRunningUntilFailure):
        return f"K({_compute_template_sig(node.child, arg_values)})"
    if isinstance(node, ReactiveSequence):
        inner = ",".join(_compute_template_sig(c, arg_values) for c in node.children)
        return f"Seq({inner})"
    if isinstance(node, Sequence):
        inner = ",".join(_compute_template_sig(c, arg_values) for c in node.children)
        return f"NSeq({inner})"
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

    def _r_ref(value):
        if isinstance(value, str):
            return _r(value)
        if isinstance(value, list):
            return [_r_ref(item) for item in value]
        if isinstance(value, dict):
            return {k: _r_ref(v) for k, v in value.items()}
        return value

    if isinstance(node, ConditionNode):
        node.fluent = _r(node.fluent)
        node.name = _r(node.name)
        if getattr(node, "execution_ref", None):
            node.execution_ref = _r_ref(node.execution_ref)
    elif isinstance(node, ActionNode):
        node.action_name = _r(node.action_name)
        node.name = _r(node.name)
        if getattr(node, "execution_ref", None):
            node.execution_ref = _r_ref(node.execution_ref)
    elif isinstance(node, ForbiddenActionNode):
        node.forbidden_action = _r(node.forbidden_action)
        node.name = _r(node.name)
    elif isinstance(node, ReactiveSequence):
        node.name = _r(node.name)
        for child in node.children:
            _replace_in_tree(child, arg_values, param_names)
    elif isinstance(node, Sequence):
        node.name = _r(node.name)
        for child in node.children:
            _replace_in_tree(child, arg_values, param_names)
    elif isinstance(node, ReactiveSelector):
        node.name = _r(node.name)
        for child in node.children:
            _replace_in_tree(child, arg_values, param_names)
    elif isinstance(node, (Inverter, KeepRunningUntilFailure)):
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


def _collect_leaves_in_order(node: BTNode) -> List[BTNode]:
    """Return ``ConditionNode``/``ActionNode`` leaves in deterministic DFS order.

    The order matches across structurally-identical subtrees (template +
    its members), so leaf positions can be aligned by index.
    """
    out: List[BTNode] = []

    def _walk(n: BTNode) -> None:
        if isinstance(n, (ConditionNode, ActionNode)):
            out.append(n)
            return
        if isinstance(n, (ReactiveSequence, ReactiveSelector, Sequence)):
            for child in n.children:
                _walk(child)
        elif isinstance(n, (Inverter, KeepRunningUntilFailure)):
            _walk(n.child)

    _walk(node)
    return out


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
        if isinstance(node, (ReactiveSequence, ReactiveSelector, Sequence)):
            for i, child in enumerate(node.children):
                _collect(child, node, i)
        elif isinstance(node, (Inverter, KeepRunningUntilFailure)):
            _collect(node.child, node, 0)

    _collect(bt.root)

    ActionEntry = Tuple[BTNode, Optional[BTNode], Optional[int], str, List[str]]
    leaf_action_info: List[ActionEntry] = []
    for node, parent, cidx in leaf_entries:
        action_node = _find_action_node(node)
        if action_node is None:
            continue
        # Skip rule subtrees that contain more than one ActionNode:
        # ``parameterize_subtrees`` keys the template's argument tuple off
        # the FIRST action only, so multi-action subtrees would silently
        # rewrite every action leaf's args to the first action's values
        # (losing the second action's distinct argument bindings).
        # See repo memory: bt_template_per_invocation_port_binding.md.
        if _count_action_leaves(node) > 1:
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

            # Detect leaves whose ``execution_ref`` varies across members
            # of this group. For each such position, allocate template
            # ports (``predicate_ref_<i>`` / ``predicate_args_<i>`` for
            # conditions, ``action_ref_<i>`` / ``action_args_<i>`` for
            # actions) and rewrite the template node so the runtime XML
            # references the port instead of inlining a single member's
            # alias. The per-invocation ``SubTreeRef`` carries the
            # original member leaves in ``leaf_refs`` so the XML writer
            # can register their refs in the alias namespace and emit
            # per-instance port values.
            template_leaves = _collect_leaves_in_order(template_tree)
            member_leaves: List[List[BTNode]] = [
                _collect_leaves_in_order(entry[0]) for entry in group
            ]
            ref_port_extras: List[str] = []
            # Per-position port-name pair (or ``None``) for use when
            # building each member's ``SubTreeRef.leaf_bindings``.
            position_ports: List[Optional[Tuple[str, str]]] = [
                None for _ in template_leaves
            ]
            for pos, tleaf in enumerate(template_leaves):
                if not getattr(tleaf, "execution_ref", None):
                    continue
                refs_at_pos = [
                    getattr(member_leaves[m][pos], "execution_ref", None)
                    for m in range(len(group))
                ]
                if all(r == refs_at_pos[0] for r in refs_at_pos[1:]):
                    continue
                if isinstance(tleaf, ConditionNode):
                    ref_port = f"predicate_ref_{pos}"
                    args_port = f"predicate_args_{pos}"
                else:
                    ref_port = f"action_ref_{pos}"
                    args_port = f"action_args_{pos}"
                # Mark the template node so xml_writer emits port-references.
                tleaf._template_ref_port = ref_port
                tleaf._template_args_port = args_port
                position_ports[pos] = (ref_port, args_port)
                ref_port_extras.extend([ref_port, args_port])

            all_param_names = param_names + ref_port_extras
            bt.templates[tid] = (template_tree, all_param_names)

            for member_idx, (node, parent, cidx, _atype, args) in enumerate(group):
                params = dict(zip(param_names, args))
                leaf_bindings: List[Optional[Tuple[BTNode, str, str]]] = []
                for pos, ports in enumerate(position_ports):
                    if ports is None:
                        leaf_bindings.append(None)
                    else:
                        ref_port, args_port = ports
                        leaf_bindings.append(
                            (member_leaves[member_idx][pos], ref_port, args_port)
                        )
                ref = SubTreeRef(tid, params, leaf_bindings=leaf_bindings)
                if parent is not None:
                    if isinstance(parent, (ReactiveSequence, ReactiveSelector, Sequence)):
                        parent.children[cidx] = ref
                    elif isinstance(parent, (Inverter, KeepRunningUntilFailure)):
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
    if isinstance(node, KeepRunningUntilFailure):
        return f"K({structural_signature(node.child)})"
    if isinstance(node, ReactiveSequence):
        inner = ",".join(structural_signature(c) for c in node.children)
        return f"Seq({inner})"
    if isinstance(node, Sequence):
        inner = ",".join(structural_signature(c) for c in node.children)
        return f"NSeq({inner})"
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
        elif isinstance(node, Sequence):
            node.children = [_dedup(c) for c in node.children]
        elif isinstance(node, ReactiveSelector):
            node.children = [_dedup(c) for c in node.children]
        elif isinstance(node, (Inverter, KeepRunningUntilFailure)):
            node.child = _dedup(node.child)

        sig = structural_signature(node)
        canonical = sig_to_node.get(sig)
        if canonical is not None:
            return canonical
        sig_to_node[sig] = node
        return node

    return _dedup(root)
