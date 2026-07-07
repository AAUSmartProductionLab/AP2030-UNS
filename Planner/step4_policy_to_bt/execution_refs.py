from __future__ import annotations

import copy
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence

from .literals import parse_predicate


def _split_negation(literal: str) -> tuple[str, bool]:
    text = str(literal or "").strip()
    lowered = text.lower()
    if lowered.startswith("not(") and text.endswith(")"):
        return text[4:-1].strip(), True
    return text, False


def _lookup_ref(
    refs: Mapping[str, Dict[str, Any]],
    refs_ci: Mapping[str, Dict[str, Any]],
    key: str,
) -> Optional[Dict[str, Any]]:
    if not key:
        return None
    exact = refs.get(key)
    if exact is not None:
        return copy.deepcopy(exact)
    lowered = refs_ci.get(key.lower())
    if lowered is not None:
        return copy.deepcopy(lowered)
    return None


def _get_ref_maps(
    planner_metadata: Optional[Mapping[str, Any]],
    *,
    key: str,
) -> tuple[Mapping[str, Dict[str, Any]], Mapping[str, Dict[str, Any]]]:
    metadata = planner_metadata or {}
    refs = metadata.get(key)
    refs_ci = metadata.get(f"{key}_ci")
    if not isinstance(refs, Mapping):
        refs = {}
    if not isinstance(refs_ci, Mapping):
        refs_ci = {str(k).lower(): v for k, v in refs.items() if isinstance(v, Mapping)}
    return refs, refs_ci


def _to_arg_list(action_args: Iterable[Any]) -> list[str]:
    result: list[str] = []
    for arg in action_args:
        text = str(arg or "").strip()
        if text:
            result.append(text)
    return result


def _get_object_ref_maps(
    planner_metadata: Optional[Mapping[str, Any]],
) -> tuple[Mapping[str, Dict[str, Any]], Mapping[str, Dict[str, Any]]]:
    metadata = planner_metadata or {}
    refs = metadata.get("object_refs")
    refs_ci = metadata.get("object_refs_ci")
    if not isinstance(refs, Mapping):
        refs = {}
    if not isinstance(refs_ci, Mapping):
        refs_ci = {str(k).lower(): v for k, v in refs.items() if isinstance(v, Mapping)}
    return refs, refs_ci


def _resolve_object_ref(
    planner_metadata: Optional[Mapping[str, Any]],
    object_name: str,
) -> Dict[str, str]:
    refs, refs_ci = _get_object_ref_maps(planner_metadata)
    entry = _lookup_ref(refs, refs_ci, str(object_name or "").strip()) or {}
    return {
        "aas_id": str(entry.get("source_aas_id") or ""),
        "aas_path": str(entry.get("object_aas_path") or entry.get("reference") or ""),
    }


def resolve_action_execution_ref(
    planner_metadata: Optional[Mapping[str, Any]],
    action_name: str,
    action_args: Sequence[Any] = (),
) -> Optional[Dict[str, Any]]:
    """Build the execution ref for an ExecuteAction BT node.

    Returns a dict with:
      - ``action_ref``: AAS URL to the skill (plain string, not JSON)
      - ``action_args``: JSON array of AAS identifiers for parameters
    """
    refs, refs_ci = _get_ref_maps(planner_metadata, key="action_refs")
    normalized_action_name = str(action_name or "").strip()
    ref = _lookup_ref(refs, refs_ci, normalized_action_name)
    if ref is None:
        token_name = normalized_action_name.split()[0] if normalized_action_name else ""
        ref = _lookup_ref(refs, refs_ci, token_name)
    if ref is None:
        return None

    arg_values = _to_arg_list(action_args)
    parameter_bindings = list(ref.get("parameter_bindings") or [])
    grounded_arguments: list[dict[str, Any]] = []
    for idx, binding in enumerate(parameter_bindings):
        value = ""
        resolved_kind = str(binding.get("resolved_kind") or "")
        if resolved_kind == "constant":
            value = str(binding.get("resolved_object") or binding.get("bound_object") or "")
        else:
            resolved_up_param = str(binding.get("resolved_up_param") or "")
            if resolved_up_param.startswith("p") and resolved_up_param[1:].isdigit():
                arg_idx = int(resolved_up_param[1:])
                if arg_idx < len(arg_values):
                    value = arg_values[arg_idx]
            if not value and idx < len(arg_values):
                value = arg_values[idx]
        grounded_arguments.append(
            {"name": str(binding.get("name") or f"p{idx}"),
             "value": value,
             "binding_kind": resolved_kind or "free"}
        )

    # Build JSON array of AAS IDs for the args.
    arg_aas_ids: list[str] = []
    for grounded in grounded_arguments:
        value = str(grounded.get("value") or "")
        object_ref = _resolve_object_ref(planner_metadata, value)
        arg_aas_ids.append(object_ref["aas_id"])

    # Build the AAS skill URL.
    source_aas_id = str(ref.get("source_aas_id") or "")
    skill_name = str(ref.get("skill_name") or "").strip()
    if not skill_name:
        legacy_path = str(ref.get("action_aas_path") or "")
        skill_name = legacy_path.rstrip("/").rsplit("/", 1)[-1] if legacy_path else \
                     normalized_action_name.split()[0] if normalized_action_name else ""

    # Construct URL: <base>/submodels/instances/<aas_id>/Skills/<skill_name>
    import json as _json
    return {
        "_action_ref": source_aas_id,  # placeholder — xml_writer builds the URL
        "_skill_name": skill_name,
        "_action_args_json": _json.dumps(arg_aas_ids, separators=(",", ":")),
    }


def resolve_predicate_execution_ref(
    planner_metadata: Optional[Mapping[str, Any]],
    literal: str,
) -> Optional[Dict[str, Any]]:
    """Build the execution ref for a FluentCheck BT node.

    Returns a dict with:
      - ``fluent_ref``: ontology predicate URI (plain string)
      - ``fluent_args``: JSON array of argument values
    """
    literal_text = str(literal or "").strip()
    base_literal, is_negated = _split_negation(literal_text)
    parsed = parse_predicate(base_literal)
    if parsed is None:
        return None
    predicate_name, arguments = parsed

    # Look up the ontology semantic ID from planner metadata.
    refs, refs_ci = _get_ref_maps(planner_metadata, key="predicate_refs")
    ref = _lookup_ref(refs, refs_ci, predicate_name)
    semantic_id = str(ref.get("semantic_id") or "").strip() if ref else ""

    # Resolve argument values: prefer AAS IDs via object_refs, fall back to literal.
    resolved_args: list[str] = []
    for arg in arguments:
        object_ref = _resolve_object_ref(planner_metadata, arg)
        aas_id = str(object_ref.get("aas_id") or "")
        if aas_id:
            resolved_args.append(aas_id)
        else:
            resolved_args.append(str(arg or "").strip())

    import json as _json
    return {
        "fluent_ref": semantic_id or predicate_name,
        "fluent_args": _json.dumps(resolved_args, separators=(",", ":")),
    }
