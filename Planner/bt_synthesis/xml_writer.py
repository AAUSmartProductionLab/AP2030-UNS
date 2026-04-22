"""
BehaviorTree.CPP v4 XML serialization.

Converts the in-memory ``BehaviorTree`` (from ``bt_nodes``) into the XML
format consumed by BehaviorTree.CPP v4, including:

- Factored subtree definitions (shared and ``is_rule_leaf`` nodes).
- Parameterized template definitions with ``{argN}`` ports.
- ``TreeNodesModel`` declarations for FluentCheck, ExecuteAction,
  GoalReached, ForbiddenAction, and template SubTrees.

Public API
----------
- ``bt_to_xml(bt, tree_id)`` — serialize a ``BehaviorTree`` to XML string.
- ``count_bt_nodes(node)`` — count all nodes in a subtree.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Set

from .nodes import (
    ActionNode,
    BTNode,
    BehaviorTree,
    ConditionNode,
    FailureLeaf,
    ForbiddenActionNode,
    Inverter,
    Sequence,
    ReactiveSelector,
    ReactiveSequence,
    SubTreeRef,
    SuccessLeaf,
    sanitize_bt_id,
)


# ===================================================================
#  Helpers
# ===================================================================


def _iter_children(node: BTNode):
    """Yield immediate children of a composite or decorator node."""
    if isinstance(node, (ReactiveSelector, ReactiveSequence, Sequence)):
        yield from node.children
    elif isinstance(node, Inverter):
        yield node.child


def _tree_uses_forbidden_action(root: BTNode) -> bool:
    """Return True when the subtree contains any ForbiddenActionNode."""
    stack: List[BTNode] = [root]
    while stack:
        node = stack.pop()
        if isinstance(node, ForbiddenActionNode):
            return True
        stack.extend(_iter_children(node))
    return False


def _collect_factorable_subtrees(root: BTNode) -> Dict[int, str]:
    """Identify subtrees to emit as named ``<BehaviorTree>`` definitions.

    Extracts ``is_rule_leaf`` nodes (always) and any node referenced more
    than once (shared via deduplication).
    """
    ref_count: Dict[int, int] = {}
    stack: List[BTNode] = [root]
    while stack:
        node = stack.pop()
        for child in _iter_children(node):
            nid = id(child)
            ref_count[nid] = ref_count.get(nid, 0) + 1
            if ref_count[nid] == 1:
                stack.append(child)

    extracted: Dict[int, str] = {}
    used_ids: Set[str] = set()

    stack = [root]
    visited: Set[int] = set()
    while stack:
        node = stack.pop()
        nid = id(node)
        if nid in visited:
            continue
        visited.add(nid)

        for child in _iter_children(node):
            stack.append(child)

        if not isinstance(node, (ReactiveSequence, ReactiveSelector, Sequence)):
            continue

        node_name = node.name or ""
        is_rule = node.is_rule_leaf
        is_shared = ref_count.get(nid, 0) >= 2
        if not (is_rule or is_shared):
            continue

        base = sanitize_bt_id(node_name) if node_name else "Shared"
        candidate = base
        idx = 2
        while candidate in used_ids:
            candidate = f"{base}_{idx}"
            idx += 1
        used_ids.add(candidate)
        extracted[nid] = candidate

    return extracted


# ===================================================================
#  Public utilities
# ===================================================================


def count_bt_nodes(node: BTNode) -> int:
    """Count all nodes in a subtree (useful for statistics)."""
    if isinstance(node, (ReactiveSelector, ReactiveSequence, Sequence)):
        return 1 + sum(count_bt_nodes(c) for c in node.children)
    if isinstance(node, Inverter):
        return 1 + count_bt_nodes(node.child)
    return 1


# ===================================================================
#  Core XML serialization
# ===================================================================


def _bt_node_to_xml(
    node: BTNode,
    parent_el: ET.Element,
    extracted_ids: Optional[Dict[int, str]] = None,
    inside_definition_of: Optional[int] = None,
) -> None:
    """Recursively serialize *node* into XML under *parent_el*."""
    if extracted_ids is None:
        extracted_ids = {}

    node_id = id(node)
    if node_id in extracted_ids and node_id != inside_definition_of:
        ET.SubElement(parent_el, "SubTree", attrib={"ID": extracted_ids[node_id]})
        return

    if isinstance(node, ReactiveSelector):
        el = ET.SubElement(parent_el, "ReactiveFallback", attrib={"name": node.name})
        for child in node.children:
            _bt_node_to_xml(child, el, extracted_ids, inside_definition_of)

    elif isinstance(node, Sequence):
        el = ET.SubElement(parent_el, "Sequence", attrib={"name": node.name})
        for child in node.children:
            _bt_node_to_xml(child, el, extracted_ids, inside_definition_of)

    elif isinstance(node, ReactiveSequence):
        el = ET.SubElement(parent_el, "ReactiveSequence", attrib={"name": node.name})
        for child in node.children:
            _bt_node_to_xml(child, el, extracted_ids, inside_definition_of)

    elif isinstance(node, Inverter):
        el = ET.SubElement(parent_el, "Inverter", attrib={"name": "Inverter"})
        _bt_node_to_xml(node.child, el, extracted_ids, inside_definition_of)

    elif isinstance(node, SubTreeRef):
        attribs = {"ID": node.template_id}
        attribs.update(node.params)
        ET.SubElement(parent_el, "SubTree", attrib=attribs)

    elif isinstance(node, ConditionNode):
        ET.SubElement(parent_el, "Condition", attrib={
            "ID": "FluentCheck",
            "name": node.fluent,
            "fluent": node.fluent,
        })

    elif isinstance(node, ActionNode):
        parts = node.action_name.split()
        action_name = parts[0] if parts else node.action_name
        action_args = " ".join(parts[1:]) if len(parts) > 1 else ""
        ET.SubElement(parent_el, "Action", attrib={
            "ID": "ExecuteAction",
            "name": node.action_name,
            "action_name": action_name,
            "action_args": action_args,
        })

    elif isinstance(node, SuccessLeaf):
        ET.SubElement(parent_el, "Action", attrib={
            "ID": "GoalReached",
            "name": "GoalReached",
        })

    elif isinstance(node, ForbiddenActionNode):
        parts = node.forbidden_action.split()
        action_name = parts[0] if parts else node.forbidden_action
        action_args = " ".join(parts[1:]) if len(parts) > 1 else ""
        ET.SubElement(parent_el, "Action", attrib={
            "ID": "ForbiddenAction",
            "name": f"Forbid:{node.forbidden_action}",
            "forbidden_action": action_name,
            "forbidden_args": action_args,
        })

    elif isinstance(node, FailureLeaf):
        ET.SubElement(parent_el, "Action", attrib={
            "ID": "AlwaysFailure",
            "name": node.name,
        })


# ===================================================================
#  Main entry point
# ===================================================================


def bt_to_xml(bt: BehaviorTree, tree_id: str = "MainTree") -> str:
    """Serialize a ``BehaviorTree`` to BehaviorTree.CPP v4 XML."""
    root_el = ET.Element("root", attrib={"BTCPP_format": "4"})
    extracted_ids = _collect_factorable_subtrees(bt.root)
    root_el.set("main_tree_to_execute", tree_id)
    # Main tree.
    bt_el = ET.SubElement(root_el, "BehaviorTree", attrib={"ID": tree_id})
    _bt_node_to_xml(bt.root, bt_el, extracted_ids)

    # Subtree definitions.
    if extracted_ids:
        id_to_node: Dict[str, BTNode] = {}
        stack: List[BTNode] = [bt.root]
        while stack:
            node = stack.pop()
            stack.extend(_iter_children(node))
            node_id = id(node)
            if node_id in extracted_ids:
                id_to_node[extracted_ids[node_id]] = node

        for subtree_id in sorted(id_to_node):
            sub_el = ET.SubElement(root_el, "BehaviorTree", attrib={"ID": subtree_id})
            node = id_to_node[subtree_id]
            _bt_node_to_xml(node, sub_el, extracted_ids, inside_definition_of=id(node))

    # Parameterized template definitions.
    templates = getattr(bt, 'templates', {})
    if templates:
        for templ_id in sorted(templates):
            templ_tree, param_names = templates[templ_id]
            templ_el = ET.SubElement(root_el, "BehaviorTree", attrib={"ID": templ_id})
            _bt_node_to_xml(templ_tree, templ_el)

    # Node model declarations.
    model = ET.SubElement(root_el, "TreeNodesModel")

    fc = ET.SubElement(model, "Condition", attrib={"ID": "FluentCheck"})
    ET.SubElement(fc, "input_port", attrib={"name": "fluent", "default": ""})

    ea = ET.SubElement(model, "Action", attrib={"ID": "ExecuteAction"})
    ET.SubElement(ea, "input_port", attrib={"name": "action_name", "default": ""})
    ET.SubElement(ea, "input_port", attrib={"name": "action_args", "default": ""})

    ET.SubElement(model, "Action", attrib={"ID": "GoalReached"})

    if _tree_uses_forbidden_action(bt.root):
        fa = ET.SubElement(model, "Action", attrib={"ID": "ForbiddenAction"})
        ET.SubElement(fa, "input_port", attrib={"name": "forbidden_action", "default": ""})
        ET.SubElement(fa, "input_port", attrib={"name": "forbidden_args", "default": ""})

    # Parameterized SubTree port declarations.
    if templates:
        for templ_id in sorted(templates):
            _templ_tree, param_names = templates[templ_id]
            st = ET.SubElement(model, "SubTree", attrib={"ID": templ_id, "editable": "true"})
            for pname in param_names:
                ET.SubElement(st, "input_port", attrib={"name": pname})

    ET.indent(root_el, space="  ")
    return ET.tostring(root_el, encoding="unicode", xml_declaration=True)
