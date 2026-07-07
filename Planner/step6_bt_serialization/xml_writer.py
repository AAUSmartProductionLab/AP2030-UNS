"""
BehaviorTree.CPP v4 XML serialization.

Converts the in-memory ``BehaviorTree`` (from ``bt_nodes``) into the XML
format consumed by BehaviorTree.CPP v4, including:

- Factored subtree definitions (shared and ``is_rule_leaf`` nodes).
- Parameterized template definitions with ``{argN}`` ports.
- ``TreeNodesModel`` declarations for FluentCheck, ExecuteAction,
  and ForbiddenAction node types.

All execution-ref payloads (action_ref, predicate_ref) are inlined
directly as XML attribute values.  No TreeNodesModel port declarations
are needed — the BT_Controller receives the JSON directly from the
attribute string.

Public API
----------
- ``bt_to_xml(bt, tree_id)`` — serialize a ``BehaviorTree`` to XML string.
- ``count_bt_nodes(node)`` — count all nodes in a subtree.
"""

from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Mapping, Optional, Set, Tuple

from ..step4_policy_to_bt.nodes import (
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
    sanitize_bt_id,
)


# ===================================================================
#  Helpers
# ===================================================================


def _iter_children(node: BTNode):
    """Yield immediate children of a composite or decorator node."""
    if isinstance(node, (ReactiveSelector, ReactiveSequence, Sequence)):
        yield from node.children
    elif isinstance(node, (Inverter, KeepRunningUntilFailure)):
        yield node.child


def _ref_to_xml_attr(ref: Dict[str, object]) -> str:
    return json.dumps(ref, separators=(",", ":"), sort_keys=True)


def _tree_uses_forbidden_action(root: BTNode) -> bool:
    """Return True when the subtree contains any ForbiddenActionNode."""
    stack: List[BTNode] = [root]
    while stack:
        node = stack.pop()
        if isinstance(node, ForbiddenActionNode):
            return True
        stack.extend(_iter_children(node))
    return False


def _build_subtree_id(
    node_name: str,
    *,
    is_rule: bool,
    is_shared: bool,
    used_ids: Set[str],
) -> str:
    """Create readable but compact deterministic subtree IDs."""
    original = sanitize_bt_id(node_name) if node_name else ""
    fallback = "Rule" if is_rule else ("Shared" if is_shared else "SubTree")
    if not original:
        original = fallback

    if len(original) <= 48:
        candidate = original
    else:
        if original.startswith("Progression"):
            prefix = "Prog"
            tail = original[len("Progression"):].lstrip("_")
        elif original.startswith("When_"):
            prefix = "When"
            tail = original[len("When_"):]
        elif original.startswith("PolicyRules"):
            prefix = "Policy"
            tail = original[len("PolicyRules"):].lstrip("_")
        elif original.startswith("GoalBranch"):
            prefix = "Goal"
            tail = original[len("GoalBranch"):].lstrip("_")
        else:
            prefix = original[:12]
            tail = original[12:]

        tail_snippet = sanitize_bt_id(tail)[:16] if tail else ""
        digest = hashlib.sha1(original.encode("utf-8")).hexdigest()[:6]
        candidate = f"{prefix}_{tail_snippet}_h{digest}" if tail_snippet else f"{prefix}_h{digest}"

    base = sanitize_bt_id(candidate) or fallback
    unique = base
    idx = 2
    while unique in used_ids:
        unique = f"{base}_{idx}"
        idx += 1
    used_ids.add(unique)
    return unique


def _compact_fallback_name(node_name: str) -> str:
    """Compact verbose ReactiveFallback names for XML readability."""
    name = str(node_name or "").strip()
    if not name:
        return "ReactiveFallback"
    if len(name) <= 64:
        return name

    clean = sanitize_bt_id(name) or "ReactiveFallback"
    if clean.startswith("Progression"):
        prefix = "Prog"
        tail = clean[len("Progression"):].lstrip("_")
    elif clean.startswith("When_"):
        prefix = "When"
        tail = clean[len("When_"):]
    elif clean.startswith("PolicyRoot"):
        prefix = "PolicyRoot"
        tail = clean[len("PolicyRoot"):].lstrip("_")
    else:
        prefix = clean[:12]
        tail = clean[12:]

    tail_snippet = sanitize_bt_id(tail)[:20] if tail else ""
    digest = hashlib.sha1(clean.encode("utf-8")).hexdigest()[:6]
    compact = f"{prefix}_{tail_snippet}_h{digest}" if tail_snippet else f"{prefix}_h{digest}"
    return sanitize_bt_id(compact)[:64] or "ReactiveFallback"


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

        extracted[nid] = _build_subtree_id(
            node_name,
            is_rule=is_rule,
            is_shared=is_shared,
            used_ids=used_ids,
        )

    return extracted


# ===================================================================
#  Public utilities
# ===================================================================


def count_bt_nodes(node: BTNode) -> int:
    """Count all nodes in a subtree (useful for statistics)."""
    if isinstance(node, (ReactiveSelector, ReactiveSequence, Sequence)):
        return 1 + sum(count_bt_nodes(c) for c in node.children)
    if isinstance(node, (Inverter, KeepRunningUntilFailure)):
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
    """Recursively serialize *node* into XML under *parent_el*.

    Execution-ref payloads are inlined directly as JSON attribute
    values — no blackboard indirection needed.
    """
    if extracted_ids is None:
        extracted_ids = {}

    node_id = id(node)
    if node_id in extracted_ids and node_id != inside_definition_of:
        ET.SubElement(
            parent_el,
            "SubTree",
            attrib={"ID": extracted_ids[node_id], "_autoremap": "true"},
        )
        return

    if isinstance(node, ReactiveSelector):
        el = ET.SubElement(parent_el, "ReactiveFallback", attrib={"name": _compact_fallback_name(node.name)})
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

    elif isinstance(node, KeepRunningUntilFailure):
        el = ET.SubElement(parent_el, "KeepRunningUntilFailure", attrib={"name": node.name})
        _bt_node_to_xml(node.child, el, extracted_ids, inside_definition_of)

    elif isinstance(node, SubTreeRef):
        attribs = {"ID": node.template_id}
        attribs.update(node.params)
        for binding in node.leaf_bindings:
            if binding is None:
                continue
            leaf, ref_port, args_port = binding
            if isinstance(leaf, ConditionNode) and leaf.execution_ref:
                attribs[ref_port] = leaf.execution_ref.get("fluent_ref", "")
                attribs[args_port] = leaf.execution_ref.get("fluent_args", "[]")
            elif isinstance(leaf, ActionNode) and leaf.execution_ref:
                src = leaf.execution_ref.get("_action_ref", "")
                sk = leaf.execution_ref.get("_skill_name", "")
                if src and sk:
                    attribs[ref_port] = f"{src}/Skills/{sk}"
                if args_port:
                    attribs[args_port] = leaf.execution_ref.get("_action_args_json", "[]")
        attribs.setdefault("_autoremap", "true")
        ET.SubElement(parent_el, "SubTree", attrib=attribs)

    elif isinstance(node, ConditionNode):
        attrib = {"name": node.fluent}
        ref_port = getattr(node, "_template_ref_port", None)
        args_port = getattr(node, "_template_args_port", None)
        if ref_port:
            attrib["fluent_ref"] = f"{{{ref_port}}}"
            if args_port:
                attrib["fluent_args"] = f"{{{args_port}}}"
        elif node.execution_ref:
            attrib["fluent_ref"] = node.execution_ref.get("fluent_ref", "")
            attrib["fluent_args"] = node.execution_ref.get("fluent_args", "[]")
        ET.SubElement(parent_el, "Predicate", attrib=attrib)

    elif isinstance(node, ActionNode):
        attrib = {"name": node.action_name}
        ref_port = getattr(node, "_template_ref_port", None)
        args_port = getattr(node, "_template_args_port", None)
        if ref_port:
            if args_port:
                attrib["action_args"] = f"{{{args_port}}}"
            attrib["action_ref"] = f"{{{ref_port}}}"
        else:
            tokens = node.action_name.split()
            if len(tokens) > 1:
                args_value = ";".join(tokens[1:])
                attrib["action_args"] = f'"{args_value}"'
            if node.execution_ref:
                source = node.execution_ref.get("_action_ref", "")
                skill = node.execution_ref.get("_skill_name", "")
                args_json = node.execution_ref.get("_action_args_json", "[]")
                if source and skill:
                    attrib["action_ref"] = f"{source}/Skills/{skill}"
                attrib["action_args"] = args_json
        ET.SubElement(parent_el, "Skill", attrib=attrib)

    elif isinstance(node, SuccessLeaf):
        ET.SubElement(parent_el, "AlwaysSuccess", attrib={
            "name": "Success",
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


def bt_to_xml(
    bt: BehaviorTree,
    tree_id: str = "MainTree",
    planner_metadata: Optional[Mapping[str, Any]] = None,
) -> str:
    """Serialize a ``BehaviorTree`` to BehaviorTree.CPP v4 XML.

    All execution-ref payloads are inlined as JSON attribute values.
    No TreeNodesModel port declarations are emitted — the BT_Controller
    receives the JSON directly from the attribute string.
    """
    root_el = ET.Element("root", attrib={"BTCPP_format": "4"})
    extracted_ids = _collect_factorable_subtrees(bt.root)
    templates = getattr(bt, 'templates', {})

    # BT.CPP v4 only applies ``<TreeNodesModel><SubTree>`` ``input_port`` ``default``
    # values when the subtree is *invoked* via a ``<SubTree>`` element. When ``tree_id``
    # is the entry point, wrap it in a ``PlannerRoot`` BehaviorTree that contains a
    # single ``<SubTree ID="<tree_id>"/>`` invocation.  With inlined refs, this is
    # only needed for the initial-state payload.
    wrapper_id = "PlannerRoot"
    root_el.set("main_tree_to_execute", wrapper_id)
    wrapper_el = ET.SubElement(root_el, "BehaviorTree", attrib={"ID": wrapper_id})
    ET.SubElement(wrapper_el, "SubTree", attrib={"ID": tree_id})

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
    if templates:
        for templ_id in sorted(templates):
            templ_tree, param_names = templates[templ_id]
            templ_el = ET.SubElement(root_el, "BehaviorTree", attrib={"ID": templ_id})
            _bt_node_to_xml(templ_tree, templ_el)

    # ── TreeNodesModel: only the basic node type declarations ──────
    model = ET.SubElement(root_el, "TreeNodesModel")

    fc = ET.SubElement(model, "Condition", attrib={"ID": "Predicate"})
    ET.SubElement(fc, "input_port", attrib={"name": "fluent_ref", "default": ""})
    ET.SubElement(fc, "input_port", attrib={"name": "fluent_args", "default": ""})

    ea = ET.SubElement(model, "Action", attrib={"ID": "Skill"})
    ET.SubElement(ea, "input_port", attrib={"name": "action_args", "default": ""})
    ET.SubElement(ea, "input_port", attrib={"name": "action_ref", "default": ""})

    if _tree_uses_forbidden_action(bt.root):
        fa = ET.SubElement(model, "Action", attrib={"ID": "ForbiddenAction"})
        ET.SubElement(fa, "input_port", attrib={"name": "forbidden_action", "default": ""})
        ET.SubElement(fa, "input_port", attrib={"name": "forbidden_args", "default": ""})

    # Parameterized SubTree port declarations.
    initial_state_payload: Optional[str] = None
    if planner_metadata is not None:
        atoms = planner_metadata.get("initial_state") if isinstance(planner_metadata, Mapping) else None
        if atoms:
            try:
                initial_state_payload = json.dumps(list(atoms), separators=(",", ":"))
            except Exception:
                initial_state_payload = None

    if initial_state_payload is not None:
        main_st = ET.SubElement(model, "SubTree", attrib={"ID": tree_id, "editable": "true"})
        ET.SubElement(
            main_st,
            "input_port",
            attrib={"name": "_planner_initial_state", "default": initial_state_payload},
        )

    if templates:
        for templ_id in sorted(templates):
            _templ_tree, param_names = templates[templ_id]
            st = ET.SubElement(model, "SubTree", attrib={"ID": templ_id, "editable": "true"})
            for pname in param_names:
                ET.SubElement(st, "input_port", attrib={"name": pname})

    # BT.CPP v4 builds each node's ``fullPath()`` as ``<subtree-prefix>/<name>``
    # and only auto-disambiguates with a UID suffix when no ``name`` attribute
    # is set (or when ``name == ID``). Sibling nodes that share the same
    # explicit ``name`` within a single ``<BehaviorTree>`` therefore collide
    # and cause ``TreeObserver`` to throw ``"TreeObserver not built correctly"``.
    # Walk every emitted BehaviorTree and uniquify duplicate names while
    # leaving inner ``<SubTree>`` invocations (own subtree namespace) alone.
    _uniquify_names_within_subtrees(root_el)

    ET.indent(root_el, space="  ")
    return ET.tostring(root_el, encoding="unicode", xml_declaration=True)


def _uniquify_names_within_subtrees(root_el: ET.Element) -> None:
    """Disambiguate duplicate ``name`` attributes inside each ``<BehaviorTree>``.

    BT.CPP composes each node's path from its containing subtree's prefix and
    its ``name`` attribute; duplicates cause ``BT::TreeObserver`` to abort with
    ``"TreeObserver not built correctly"``. Each ``<BehaviorTree>`` is its own
    subtree namespace, so we walk one tree at a time. ``<SubTree>`` invocation
    elements start a *new* subtree namespace and are not descended into.
    """
    for bt_el in root_el.findall("BehaviorTree"):
        used: Dict[str, int] = {}

        def _visit(el: ET.Element) -> None:
            name = el.attrib.get("name")
            if name:
                count = used.get(name, 0)
                if count >= 1:
                    el.set("name", f"{name}_{count + 1}")
                used[name] = count + 1
            for child in el:
                # ``<SubTree>`` invocations live in a separate path namespace
                # within BT.CPP; do not include their descendants when checking
                # for duplicates in the current subtree.
                if child.tag == "SubTree":
                    continue
                _visit(child)

        for child in bt_el:
            _visit(child)
