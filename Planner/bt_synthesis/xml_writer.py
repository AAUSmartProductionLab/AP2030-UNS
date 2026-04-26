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

import hashlib
import json
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Mapping, Optional, Set, Tuple

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


def _ref_token(value: object, *, trim_aas_suffix: bool = True) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    token = text.rstrip("/")
    if "/" in token:
        token = token.split("/")[-1]
    if "#" in token:
        token = token.split("#")[-1]
    token = sanitize_bt_id(token)
    if trim_aas_suffix and token.endswith("AAS") and len(token) > 3:
        token = token[:-3]
    return token


def _unique_key(base: str, used_keys: Set[str]) -> str:
    key = sanitize_bt_id(base) or "Ref"
    candidate = key
    idx = 2
    while candidate in used_keys:
        candidate = f"{key}_{idx}"
        idx += 1
    used_keys.add(candidate)
    return candidate


def _collect_execution_ref_aliases(
    roots: List[BTNode],
) -> tuple[Dict[int, str], List[Tuple[str, str]], Dict[int, List[str]]]:
    """Collect deterministic named blackboard aliases for execution refs."""
    entries: List[Tuple[int, str, Dict[str, object], str]] = []
    stack: List[BTNode] = list(roots)
    while stack:
        node = stack.pop()
        stack.extend(_iter_children(node))
        if isinstance(node, ConditionNode) and node.execution_ref:
            serialized = _ref_to_xml_attr(node.execution_ref)
            entries.append((id(node), "predicate", dict(node.execution_ref), serialized))
        elif isinstance(node, ActionNode) and node.execution_ref:
            serialized = _ref_to_xml_attr(node.execution_ref)
            entries.append((id(node), "action", dict(node.execution_ref), serialized))

    used_keys: Set[str] = set()
    declarations: List[Tuple[str, str]] = []

    # Create parameter AAS-link macros once so action/predicate refs can refer to them.
    parameter_links: Dict[Tuple[str, str], str] = {}
    unique_parameter_links: Set[Tuple[str, str]] = set()
    for _, _, ref, _ in entries:
        for item in list(ref.get("parameter_refs") or []):
            if not isinstance(item, dict):
                continue
            aas_id = str(item.get("aas_id") or "")
            aas_path = str(item.get("aas_path") or "")
            if aas_id or aas_path:
                unique_parameter_links.add((aas_id, aas_path))

    for aas_id, aas_path in sorted(unique_parameter_links):
        param_token = _ref_token(aas_path) or _ref_token(aas_id) or "Parameter"
        key = _unique_key(f"Param_{param_token}", used_keys)
        parameter_links[(aas_id, aas_path)] = key
        declarations.append(
            (
                key,
                _ref_to_xml_attr({
                    "aas_id": aas_id,
                    "aas_path": aas_path,
                }),
            )
        )

    # Build link macros for action/fluent locations and readable macros for full refs.
    unique_refs: Dict[Tuple[str, str], Dict[str, object]] = {}
    for _, kind, ref, serialized in entries:
        unique_refs.setdefault((kind, serialized), ref)

    payload_key_by_kind_and_serialized: Dict[Tuple[str, str], str] = {}
    payload_arg_links_by_kind_and_serialized: Dict[Tuple[str, str], List[str]] = {}
    ref_records: List[Tuple[str, str, str, Dict[str, object]]] = []
    for (kind, serialized), ref in unique_refs.items():
        if kind == "predicate":
            fluent_token = _ref_token(ref.get("fluent_aas_path"), trim_aas_suffix=False) or "Predicate"
            param_refs = list(ref.get("parameter_refs") or [])
            first_param = param_refs[0] if param_refs and isinstance(param_refs[0], dict) else {}
            object_token = _ref_token(first_param.get("aas_path")) or _ref_token(ref.get("source_aas_id")) or "Object"
            readable_base = f"{fluent_token}_{object_token}"
            link_base = f"FluentLink_{fluent_token}_{object_token}"
            link_payload = {
                "aas_id": str(ref.get("source_aas_id") or ""),
                "aas_path": str(ref.get("fluent_aas_path") or ""),
            }
        else:
            action_token = _ref_token(ref.get("action_aas_path"), trim_aas_suffix=False) or "Action"
            source_token = _ref_token(ref.get("source_aas_id")) or "Source"
            readable_base = f"{action_token}_{source_token}"
            link_base = f"ActionLink_{action_token}_{source_token}"
            link_payload = {
                "aas_id": str(ref.get("source_aas_id") or ""),
                "aas_path": str(ref.get("action_aas_path") or ""),
            }

        link_key = _unique_key(link_base, used_keys)
        declarations.append((link_key, _ref_to_xml_attr(link_payload)))
        ref_records.append((kind, serialized, readable_base, ref | {"_aas_link_key": link_key}))

    for kind, serialized, readable_base, ref in sorted(ref_records, key=lambda x: (x[0], x[2], x[1])):
        ref_key = _unique_key(readable_base, used_keys)

        parameter_link_keys: List[str] = []
        for item in list(ref.get("parameter_refs") or []):
            if not isinstance(item, dict):
                continue
            aas_id = str(item.get("aas_id") or "")
            aas_path = str(item.get("aas_path") or "")
            key = parameter_links.get((aas_id, aas_path))
            if key:
                parameter_link_keys.append(key)

        enriched = dict(ref)
        enriched.pop("_aas_link_key", None)
        if parameter_link_keys:
            enriched["parameter_link_keys"] = parameter_link_keys
        aas_link_key = str(ref.get("_aas_link_key") or "")
        if aas_link_key:
            enriched["aas_link_key"] = aas_link_key

        declarations.append((ref_key, _ref_to_xml_attr(enriched)))
        payload_key_by_kind_and_serialized[(kind, serialized)] = ref_key
        payload_arg_links_by_kind_and_serialized[(kind, serialized)] = list(parameter_link_keys)

    node_aliases: Dict[int, str] = {}
    node_arg_links: Dict[int, List[str]] = {}
    for node_id, kind, _, serialized in entries:
        alias = payload_key_by_kind_and_serialized.get((kind, serialized))
        if alias:
            node_aliases[node_id] = alias
            node_arg_links[node_id] = payload_arg_links_by_kind_and_serialized.get((kind, serialized), [])

    return node_aliases, declarations, node_arg_links


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
    execution_ref_aliases: Optional[Dict[int, str]] = None,
    execution_arg_aliases: Optional[Dict[int, List[str]]] = None,
) -> None:
    """Recursively serialize *node* into XML under *parent_el*."""
    if extracted_ids is None:
        extracted_ids = {}
    if execution_ref_aliases is None:
        execution_ref_aliases = {}
    if execution_arg_aliases is None:
        execution_arg_aliases = {}

    node_id = id(node)
    if node_id in extracted_ids and node_id != inside_definition_of:
        ET.SubElement(parent_el, "SubTree", attrib={"ID": extracted_ids[node_id]})
        return

    if isinstance(node, ReactiveSelector):
        el = ET.SubElement(parent_el, "ReactiveFallback", attrib={"name": _compact_fallback_name(node.name)})
        for child in node.children:
            _bt_node_to_xml(
                child,
                el,
                extracted_ids,
                inside_definition_of,
                execution_ref_aliases,
                execution_arg_aliases,
            )

    elif isinstance(node, Sequence):
        el = ET.SubElement(parent_el, "Sequence", attrib={"name": node.name})
        for child in node.children:
            _bt_node_to_xml(
                child,
                el,
                extracted_ids,
                inside_definition_of,
                execution_ref_aliases,
                execution_arg_aliases,
            )

    elif isinstance(node, ReactiveSequence):
        el = ET.SubElement(parent_el, "ReactiveSequence", attrib={"name": node.name})
        for child in node.children:
            _bt_node_to_xml(
                child,
                el,
                extracted_ids,
                inside_definition_of,
                execution_ref_aliases,
                execution_arg_aliases,
            )

    elif isinstance(node, Inverter):
        el = ET.SubElement(parent_el, "Inverter", attrib={"name": "Inverter"})
        _bt_node_to_xml(
            node.child,
            el,
            extracted_ids,
            inside_definition_of,
            execution_ref_aliases,
            execution_arg_aliases,
        )

    elif isinstance(node, KeepRunningUntilFailure):
        el = ET.SubElement(parent_el, "KeepRunningUntilFailure", attrib={"name": node.name})
        _bt_node_to_xml(
            node.child,
            el,
            extracted_ids,
            inside_definition_of,
            execution_ref_aliases,
            execution_arg_aliases,
        )

    elif isinstance(node, SubTreeRef):
        attribs = {"ID": node.template_id}
        attribs.update(node.params)
        ET.SubElement(parent_el, "SubTree", attrib=attribs)

    elif isinstance(node, ConditionNode):
        attrib = {
            "ID": "FluentCheck",
            "name": node.fluent,
        }
        if node.execution_ref:
            alias = execution_ref_aliases.get(id(node))
            if alias:
                attrib["predicate_ref"] = f"{{{alias}}}"
            else:
                attrib["predicate_ref"] = _ref_to_xml_attr(node.execution_ref)

            arg_aliases = execution_arg_aliases.get(id(node), [])
            if arg_aliases:
                args_value = ";".join(f"{{{arg_key}}}" for arg_key in arg_aliases)
                attrib["predicate_args"] = f'"{args_value}"'
        ET.SubElement(parent_el, "Condition", attrib=attrib)

    elif isinstance(node, ActionNode):
        attrib = {
            "ID": "ExecuteAction",
            "name": node.action_name,
        }
        arg_aliases = execution_arg_aliases.get(id(node), [])
        if arg_aliases:
            args_value = ";".join(f"{{{arg_key}}}" for arg_key in arg_aliases)
            attrib["action_args"] = f'"{args_value}"'
        if node.execution_ref:
            alias = execution_ref_aliases.get(id(node))
            if alias:
                attrib["action_ref"] = f"{{{alias}}}"
            else:
                attrib["action_ref"] = _ref_to_xml_attr(node.execution_ref)
        ET.SubElement(parent_el, "Action", attrib=attrib)

    elif isinstance(node, SuccessLeaf):
        ET.SubElement(parent_el, "AlwaysSuccess", attrib={
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


def bt_to_xml(
    bt: BehaviorTree,
    tree_id: str = "MainTree",
    planner_metadata: Optional[Mapping[str, Any]] = None,
) -> str:
    """Serialize a ``BehaviorTree`` to BehaviorTree.CPP v4 XML."""
    root_el = ET.Element("root", attrib={"BTCPP_format": "4"})
    extracted_ids = _collect_factorable_subtrees(bt.root)
    templates = getattr(bt, 'templates', {})
    alias_roots: List[BTNode] = [bt.root]
    if templates:
        for templ_tree, _param_names in templates.values():
            alias_roots.append(templ_tree)
    execution_ref_aliases, blackboard_declarations, execution_arg_aliases = _collect_execution_ref_aliases(alias_roots)
    root_el.set("main_tree_to_execute", tree_id)
    # Main tree.
    bt_el = ET.SubElement(root_el, "BehaviorTree", attrib={"ID": tree_id})
    _bt_node_to_xml(
        bt.root,
        bt_el,
        extracted_ids,
        execution_ref_aliases=execution_ref_aliases,
        execution_arg_aliases=execution_arg_aliases,
    )

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
            _bt_node_to_xml(
                node,
                sub_el,
                extracted_ids,
                inside_definition_of=id(node),
                execution_ref_aliases=execution_ref_aliases,
                execution_arg_aliases=execution_arg_aliases,
            )

    # Parameterized template definitions.
    if templates:
        for templ_id in sorted(templates):
            templ_tree, param_names = templates[templ_id]
            templ_el = ET.SubElement(root_el, "BehaviorTree", attrib={"ID": templ_id})
            _bt_node_to_xml(
                templ_tree,
                templ_el,
                execution_ref_aliases=execution_ref_aliases,
                execution_arg_aliases=execution_arg_aliases,
            )

    # Node model declarations.
    model = ET.SubElement(root_el, "TreeNodesModel")

    fc = ET.SubElement(model, "Condition", attrib={"ID": "FluentCheck"})
    ET.SubElement(fc, "input_port", attrib={"name": "predicate_ref", "default": ""})
    ET.SubElement(fc, "input_port", attrib={"name": "predicate_args", "default": ""})

    ea = ET.SubElement(model, "Action", attrib={"ID": "ExecuteAction"})
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

    if blackboard_declarations or initial_state_payload:
        main_st = ET.SubElement(model, "SubTree", attrib={"ID": tree_id, "editable": "true"})
        for output_key, value in blackboard_declarations or []:
            ET.SubElement(main_st, "input_port", attrib={"name": output_key, "default": value})
        if initial_state_payload is not None:
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

    ET.indent(root_el, space="  ")
    return ET.tostring(root_el, encoding="unicode", xml_declaration=True)
