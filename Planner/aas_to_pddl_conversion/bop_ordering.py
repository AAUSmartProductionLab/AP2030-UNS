from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional

from .utils import match_capability, safe_id


def compile_bop_ordering(
    merged: Dict[str, Any],
    bop_config: Optional[Dict[str, Any]],
    warnings: List[str],
) -> Dict[str, Any]:
    """Inject BoP ordering predicates and step-specific action variants."""
    if not bop_config:
        return merged

    steps = extract_bop_steps(bop_config)
    if not steps:
        warnings.append("BillOfProcesses was provided but no process steps were parsed for ordering.")
        return merged

    product_binding = resolve_order_product_binding(merged)
    step_names = ensure_step_objects(merged, steps)
    next_step_name = build_next_step_lookup(steps, step_names)
    ensure_ordering_fluents(merged)
    append_step_init_and_goal_terms(merged, product_binding, steps, step_names)

    original_actions = list(merged.get("actions", []))
    reordered_actions: List[Dict[str, Any]] = []

    for action in original_actions:
        matched_steps = [step for step in steps if action_matches_step(action, step)]
        if not matched_steps:
            reordered_actions.append(action)
            continue

        if str(action.get("action_kind") or "Action") != "Action":
            warnings.append(
                f"Action '{action.get('key')}' matched BoP capability but is not InstantaneousAction; kept unchanged."
            )
            reordered_actions.append(action)
            continue

        for step in matched_steps:
            step_name = step_names[step["id"]]
            variant = make_step_scoped_action(
                action,
                product_binding,
                step_name,
                step,
                next_step_name.get(step["id"]),
            )
            reordered_actions.append(variant)

    merged["actions"] = reordered_actions

    for step in steps:
        if not any(action_matches_step(action, step) for action in original_actions):
            warnings.append(
                f"No AIPlanning action matched BoP step '{step['name']}' ({step['semantic_id'] or 'no semantic_id'})."
            )

    return merged


def extract_bop_steps(bop_config: Dict[str, Any]) -> List[Dict[str, Any]]:
    processes = bop_config.get("Processes")
    if not isinstance(processes, list):
        return []

    raw_steps: List[Dict[str, Any]] = []
    for idx, process in enumerate(processes, start=1):
        name, config = unpack_process_entry(process, idx)
        if not config:
            continue

        semantic_id = parse_semantic_id(
            config.get("semantic_id") or config.get("process_semantic_id") or config.get("semanticId")
        )
        step_number = parse_step_number(config.get("step"), default_value=idx)

        raw_steps.append(
            {
                "id": f"step_{idx}",
                "name": str(name or f"Step{idx}"),
                "step": step_number,
                "semantic_id": semantic_id,
            }
        )

    return sorted(raw_steps, key=lambda entry: (entry["step"], entry["id"]))


def unpack_process_entry(process: Any, idx: int) -> tuple[str, Dict[str, Any]]:
    if isinstance(process, dict) and len(process) == 1:
        name = next(iter(process.keys()))
        config = process.get(name)
        if isinstance(config, dict):
            return str(name), config

    if isinstance(process, dict):
        name = process.get("idShort") or process.get("name") or f"Step{idx}"
        return str(name), process

    return f"Step{idx}", {}


def parse_semantic_id(value: Any) -> str:
    if not value:
        return ""

    if isinstance(value, str):
        return value

    if isinstance(value, dict):
        keys = value.get("keys") or []
        if keys:
            return str(keys[0].get("value") or "")

    return str(value)


def parse_step_number(value: Any, default_value: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default_value


def resolve_order_product_binding(merged: Dict[str, Any]) -> Dict[str, Any]:
    product_object = None
    for obj in merged.get("objects", []):
        declared_type = str(obj.get("declared_type") or "")
        name = str(obj.get("name") or "")
        if "product" in declared_type.lower() or "product" in name.lower():
            product_object = obj
            break

    if product_object is None:
        existing_names = {str(obj.get("name") or "") for obj in merged.get("objects", [])}
        base_name = "order_product"
        candidate = base_name
        suffix = 2
        while candidate in existing_names:
            candidate = f"{base_name}_{suffix}"
            suffix += 1

        product_object = {
            "name": candidate,
            "reference": "",
            "declared_type": "Entity",
            "source_aas_id": "",
            "source_aas_name": "BoPOrdering",
        }
        merged.setdefault("objects", []).append(product_object)

    return {"kind": "object", "name": product_object["name"]}


def ensure_step_objects(merged: Dict[str, Any], steps: List[Dict[str, Any]]) -> Dict[str, str]:
    names: Dict[str, str] = {}
    existing_names = {str(obj.get("name") or "") for obj in merged.get("objects", [])}

    for idx, step in enumerate(steps, start=1):
        slug = safe_id(step["name"]).lower()
        base_name = f"step_{idx}_{slug}" if slug else f"step_{idx}"
        candidate = base_name
        suffix = 2
        while candidate in existing_names:
            candidate = f"{base_name}_{suffix}"
            suffix += 1

        merged.setdefault("objects", []).append(
            {
                "name": candidate,
                "reference": "",
                "declared_type": "Step",
                "source_aas_id": "",
                "source_aas_name": "BoPOrdering",
            }
        )
        existing_names.add(candidate)
        names[step["id"]] = candidate

    return names


def build_next_step_lookup(steps: List[Dict[str, Any]], step_names: Dict[str, str]) -> Dict[str, Optional[str]]:
    next_lookup: Dict[str, Optional[str]] = {}
    for idx, step in enumerate(steps):
        if idx + 1 < len(steps):
            next_lookup[step["id"]] = step_names[steps[idx + 1]["id"]]
        else:
            next_lookup[step["id"]] = None
    return next_lookup


def ensure_ordering_fluents(merged: Dict[str, Any]) -> None:
    ensure_fluent(
        merged,
        {
            "key": "step_ready",
            "semantic_id": "",
            "param_types": ["Entity", "Step"],
            "transformation": None,
            "value_type": "bool",
            "source": "BoPOrdering",
        },
    )
    ensure_fluent(
        merged,
        {
            "key": "step_done",
            "semantic_id": "",
            "param_types": ["Entity", "Step"],
            "transformation": None,
            "value_type": "bool",
            "source": "BoPOrdering",
        },
    )


def ensure_fluent(merged: Dict[str, Any], fluent: Dict[str, Any]) -> None:
    existing = merged.setdefault("fluents", [])
    for current in existing:
        if current.get("key") == fluent["key"]:
            return
    existing.append(fluent)


def append_step_init_and_goal_terms(
    merged: Dict[str, Any],
    product_binding: Dict[str, Any],
    steps: List[Dict[str, Any]],
    step_names: Dict[str, str],
) -> None:
    for idx, step in enumerate(steps):
        step_binding = {"kind": "object", "name": step_names[step["id"]]}

        done_term = {
            "kind": "op",
            "op": "not",
            "children": [make_step_atom("step_done", product_binding, step_binding)],
        }
        merged.setdefault("init_terms", []).append(done_term)

        if idx == 0:
            merged.setdefault("init_terms", []).append(make_step_atom("step_ready", product_binding, step_binding))
        else:
            merged.setdefault("init_terms", []).append(
                {
                    "kind": "op",
                    "op": "not",
                    "children": [make_step_atom("step_ready", product_binding, step_binding)],
                }
            )

    last_step_binding = {"kind": "object", "name": step_names[steps[-1]["id"]]}
    merged.setdefault("goal_terms", []).append(make_step_atom("step_done", product_binding, last_step_binding))


def action_matches_step(action: Dict[str, Any], step: Dict[str, Any]) -> bool:
    required = parse_semantic_id(step.get("semantic_id"))
    if not required:
        return False

    raw_candidates = action.get("semantic_ids")
    candidates: List[str] = [candidate for candidate in (raw_candidates or []) if candidate]
    if not candidates and action.get("semantic_id"):
        candidates = [str(action.get("semantic_id"))]

    for candidate in candidates:
        if match_capability(required, candidate):
            return True

    return False


def make_step_scoped_action(
    action: Dict[str, Any],
    product_binding: Dict[str, Any],
    step_name: str,
    step: Dict[str, Any],
    next_step_name: Optional[str],
) -> Dict[str, Any]:
    cloned = copy.deepcopy(action)
    suffix = safe_id(step_name)
    cloned["key"] = f"{action['key']}__{suffix}" if suffix else f"{action['key']}__step"

    step_binding = {"kind": "object", "name": step_name}
    ready_atom = make_step_atom("step_ready", product_binding, step_binding)
    done_atom = make_step_atom("step_done", product_binding, step_binding)

    cloned.setdefault("preconditions", []).append(ready_atom)
    cloned["preconditions"].append(
        {
            "kind": "op",
            "op": "not",
            "children": [done_atom],
        }
    )

    cloned.setdefault("effects", []).append(done_atom)
    cloned["effects"].append(
        {
            "kind": "op",
            "op": "not",
            "children": [ready_atom],
        }
    )
    if next_step_name:
        cloned["effects"].append(
            make_step_atom(
                "step_ready",
                product_binding,
                {"kind": "object", "name": next_step_name},
            )
        )

    cloned["bop_step"] = {
        "name": step.get("name"),
        "order": step.get("step"),
        "semantic_id": step.get("semantic_id"),
    }

    return cloned


def make_step_atom(fluent: str, product_binding: Dict[str, Any], step_binding: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "kind": "atom",
        "fluent": fluent,
        "params": [
            dict(product_binding),
            dict(step_binding),
        ],
    }
