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
            {
                "name": str(binding.get("name") or f"p{idx}"),
                "value": value,
                "binding_kind": resolved_kind or "free",
            }
        )

    parameter_refs: list[Dict[str, Any]] = []
    for grounded in grounded_arguments:
        value = str(grounded.get("value") or "")
        object_ref = _resolve_object_ref(planner_metadata, value)
        parameter_refs.append(
            {
                "name": str(grounded.get("name") or ""),
                "aas_id": object_ref["aas_id"],
                "aas_path": object_ref["aas_path"],
            }
        )

    return {
        "source_aas_id": str(ref.get("source_aas_id") or ""),
        "action_aas_path": str(ref.get("action_aas_path") or ""),
        "transformation_aas_path": str(ref.get("transformation_aas_path") or ""),
        "parameter_refs": parameter_refs,
        # PR4: pass through pre-grounded symbolic effects so the BT
        # runtime can update SymbolicState on action SUCCESS.
        "effects": list(ref.get("effects") or []),
    }


def resolve_predicate_execution_ref(
    planner_metadata: Optional[Mapping[str, Any]],
    literal: str,
) -> Optional[Dict[str, Any]]:
    refs, refs_ci = _get_ref_maps(planner_metadata, key="predicate_refs")
    literal_text = str(literal or "").strip()
    base_literal, is_negated = _split_negation(literal_text)
    parsed = parse_predicate(base_literal)
    predicate_name = parsed[0] if parsed else base_literal
    arguments = parsed[1] if parsed else []

    ref = _lookup_ref(refs, refs_ci, predicate_name)
    if ref is None:
        return None

    _ = is_negated
    parameter_refs: list[Dict[str, Any]] = []
    for idx, arg in enumerate(arguments):
        object_ref = _resolve_object_ref(planner_metadata, arg)
        parameter_refs.append(
            {
                "name": f"p{idx}",
                "aas_id": object_ref["aas_id"],
                "aas_path": object_ref["aas_path"],
            }
        )

    source_bindings = list(ref.get("source_bindings") or [])
    binding_by_aas_id: Dict[str, Dict[str, Any]] = {}
    for binding in source_bindings:
        if not isinstance(binding, Mapping):
            continue
        aas_id = str(binding.get("aas_id") or "")
        if aas_id and aas_id not in binding_by_aas_id:
            binding_by_aas_id[aas_id] = dict(binding)

    selected_binding: Dict[str, Any] = {}
    for param_ref in parameter_refs:
        param_aas_id = str(param_ref.get("aas_id") or "")
        if not param_aas_id:
            continue
        candidate = binding_by_aas_id.get(param_aas_id)
        if candidate:
            selected_binding = candidate
            break

    return {
        "source_aas_id": str(
            selected_binding.get("aas_id")
            or ref.get("source_aas_id")
            or ""
        ),
        "fluent_aas_path": str(
            selected_binding.get("fluent_aas_path")
            or ref.get("fluent_aas_path")
            or ""
        ),
        "transformation_aas_path": str(
            selected_binding.get("transformation_aas_path")
            or ref.get("transformation_aas_path")
            or ""
        ),
        "parameter_refs": parameter_refs,
    }
