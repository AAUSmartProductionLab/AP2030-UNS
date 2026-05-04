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

    product_bindings, product_names, product_types = discover_product_bindings(merged)
    step_names = ensure_step_objects(merged, steps)
    next_step_name = build_next_step_lookup(steps, step_names)
    ensure_ordering_fluents(merged)
    if product_bindings:
        append_step_init_and_goal_terms(merged, product_bindings, steps, step_names)
    else:
        warnings.append(
            "BoP ordering could not identify product objects for per-instance step state."
        )

    original_actions = list(merged.get("actions", []))
    step_sources = build_step_sources(steps, original_actions)
    reordered_actions: List[Dict[str, Any]] = []

    for action in original_actions:
        product_binding = resolve_action_product_binding(action, product_names, product_types)
        matched_steps = [step for step in steps if action_matches_step(action, step)]
        if not matched_steps:
            if should_step_gate_occupy(action):
                occupied_steps = [step for step in steps if action_targets_step_source(action, step_sources.get(step["id"], []))]
                if occupied_steps:
                    if product_binding is None:
                        warnings.append(
                            f"Action '{action.get('key')}' requires BoP occupy gating but has no product parameter; kept unchanged."
                        )
                        reordered_actions.append(action)
                        continue
                    for step in occupied_steps:
                        step_name = step_names[step["id"]]
                        reordered_actions.append(make_step_gated_occupy_action(action, product_binding, step_name, step))
                    continue
            reordered_actions.append(action)
            continue

        if str(action.get("action_kind") or "Action") != "Action":
            warnings.append(
                f"Action '{action.get('key')}' matched BoP capability but is not InstantaneousAction; kept unchanged."
            )
            reordered_actions.append(action)
            continue

        if product_binding is None:
            warnings.append(
                f"Action '{action.get('key')}' matched BoP capability but has no product parameter; kept unchanged."
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


def build_step_sources(steps: List[Dict[str, Any]], actions: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    step_sources: Dict[str, List[str]] = {step["id"]: [] for step in steps}

    for step in steps:
        collected: List[str] = []
        for action in actions:
            if str(action.get("action_kind") or "Action") != "Action":
                continue
            if not action_matches_step(action, step):
                continue

            source_name = extract_action_source_name(action)
            if source_name and source_name not in collected:
                collected.append(source_name)

        step_sources[step["id"]] = collected

    return step_sources


def extract_action_source_name(action: Dict[str, Any]) -> str:
    direct = str(action.get("source_name") or "").strip()
    if direct:
        return direct

    sources = action.get("sources") or []
    if isinstance(sources, list) and sources:
        first = sources[0]
        if isinstance(first, (list, tuple)) and len(first) >= 2:
            return str(first[1] or "").strip()
        if isinstance(first, str):
            return first.strip()

    return ""


def should_step_gate_occupy(action: Dict[str, Any]) -> bool:
    if str(action.get("action_kind") or "Action") != "Action":
        return False

    raw_candidates = action.get("semantic_ids")
    candidates: List[str] = [candidate for candidate in (raw_candidates or []) if candidate]
    if not candidates and action.get("semantic_id"):
        candidates = [str(action.get("semantic_id"))]

    for candidate in candidates:
        if match_capability("http://www.w3id.org/aau-ra/cssx#OccupyCapability", candidate):
            return True

    return False


def action_targets_step_source(action: Dict[str, Any], step_sources: List[str]) -> bool:
    if not step_sources:
        return False

    source_name = extract_action_source_name(action)
    if not source_name:
        return False

    return source_name in step_sources


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


def discover_product_bindings(
    merged: Dict[str, Any],
) -> tuple[List[Dict[str, Any]], set[str], set[str]]:
    objects = merged.get("objects", []) or []
    by_name = {str(obj.get("name") or ""): obj for obj in objects}

    product_names: List[str] = []
    product_name_set: set[str] = set()
    product_types: set[str] = set()

    for obj in objects:
        name = str(obj.get("name") or "")
        if not name:
            continue
        declared_type = str(obj.get("declared_type") or "")
        if _looks_like_product_type(declared_type) or "product" in name.lower():
            if name not in product_name_set:
                product_names.append(name)
                product_name_set.add(name)
            if declared_type:
                product_types.add(declared_type)

    for term in merged.get("goal_terms", []) or []:
        for atom in _iter_atoms(term):
            if str(atom.get("fluent") or "").lower() != "finished":
                continue
            params = atom.get("params") or []
            if not params:
                continue
            first = params[0]
            if first.get("kind") != "object":
                continue
            name = str(first.get("name") or "")
            if not name:
                continue
            if name not in product_name_set:
                product_names.append(name)
                product_name_set.add(name)
            declared_type = str((by_name.get(name) or {}).get("declared_type") or "")
            if declared_type:
                product_types.add(declared_type)

    bindings = [{"kind": "object", "name": name} for name in product_names]
    return bindings, set(product_names), product_types


def _looks_like_product_type(type_name: str) -> bool:
    return "product" in str(type_name or "").lower()


def _iter_atoms(term: Any) -> List[Dict[str, Any]]:
    if not isinstance(term, dict):
        return []
    if term.get("kind") == "atom":
        return [term]
    if term.get("kind") == "op":
        atoms: List[Dict[str, Any]] = []
        for child in term.get("children", []) or []:
            atoms.extend(_iter_atoms(child))
        return atoms
    return []


def resolve_action_product_binding(
    action: Dict[str, Any],
    product_names: set[str],
    product_types: set[str],
) -> Optional[Dict[str, Any]]:
    parameters = action.get("parameters") or []
    if not isinstance(parameters, list):
        return None

    for idx, parameter in enumerate(parameters):
        param_type = str(parameter.get("type") or "")
        param_name = str(parameter.get("name") or "")
        bound_object = str(parameter.get("bound_object") or "")

        if _looks_like_product_type(param_type):
            return {"kind": "action_param", "index": idx}
        if param_type and param_type in product_types:
            return {"kind": "action_param", "index": idx}
        if bound_object and bound_object in product_names:
            return {"kind": "action_param", "index": idx}
        if "product" in param_name.lower():
            return {"kind": "action_param", "index": idx}

    return None


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
            "param_types": ["Product", "Step"],
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
            "param_types": ["Product", "Step"],
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
    product_bindings: List[Dict[str, Any]],
    steps: List[Dict[str, Any]],
    step_names: Dict[str, str],
) -> None:
    for product_binding in product_bindings:
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


def _term_has_positive_atom(term: Any) -> bool:
    """Return True if the term tree contains at least one positive atom.

    Used to distinguish "success" oneof branches (which set positive
    fluents and therefore advance the BoP step) from pure-negation
    "failure/retry" branches (which only assert that something did not
    happen and should leave the step unchanged so it can be retried).
    """
    if not isinstance(term, dict):
        return False
    kind = term.get("kind")
    if kind == "atom":
        return True
    if kind == "op":
        op = term.get("op")
        if op == "not":
            return False
        if op in ("and", "or"):
            return any(_term_has_positive_atom(c) for c in term.get("children", []))
        # Don't recurse into nested oneofs when classifying a branch.
        return False
    return False


def inject_step_advance_into_effects(
    action: Dict[str, Any],
    advance_terms: List[Dict[str, Any]],
) -> None:
    """Append step-advance terms to the action's effects.

    For deterministic actions (or actions whose oneof effects sit
    alongside at least one deterministic positive effect), the advance
    terms are appended at the top level so they always fire. This
    matches the previous behaviour and is correct for actions like
    capture/inspection where the step is considered done regardless of
    the non-deterministic outcome (e.g. QualityOk vs not QualityOk).

    For actions whose only top-level effect is a oneof (e.g. loading,
    where the success branch sets On/ProductAt and the failure branch
    only negates On), the advance terms are pushed into each oneof
    branch that contains at least one positive atom. Pure-negation
    branches are left untouched so step_ready stays true and step_done
    stays false, allowing the planner to retry the action.
    """
    effects = action.setdefault("effects", [])

    oneof_index = next(
        (
            i
            for i, eff in enumerate(effects)
            if isinstance(eff, dict)
            and eff.get("kind") == "op"
            and eff.get("op") == "oneof"
        ),
        None,
    )

    has_deterministic_positive = any(
        _term_has_positive_atom(eff)
        for i, eff in enumerate(effects)
        if i != oneof_index
    )

    if oneof_index is None or has_deterministic_positive:
        effects.extend(copy.deepcopy(advance_terms))
        return

    oneof = effects[oneof_index]
    children = oneof.setdefault("children", [])
    for i, branch in enumerate(children):
        if not _term_has_positive_atom(branch):
            # Failure / retry branch — leave step state unchanged.
            continue
        advance_copy = copy.deepcopy(advance_terms)
        if (
            isinstance(branch, dict)
            and branch.get("kind") == "op"
            and branch.get("op") == "and"
        ):
            branch.setdefault("children", []).extend(advance_copy)
        else:
            children[i] = {
                "kind": "op",
                "op": "and",
                "children": [branch, *advance_copy],
            }


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

    advance_terms: List[Dict[str, Any]] = [
        done_atom,
        {
            "kind": "op",
            "op": "not",
            "children": [ready_atom],
        },
    ]
    if next_step_name:
        advance_terms.append(
            make_step_atom(
                "step_ready",
                product_binding,
                {"kind": "object", "name": next_step_name},
            )
        )

    inject_step_advance_into_effects(cloned, advance_terms)

    cloned["bop_step"] = {
        "name": step.get("name"),
        "order": step.get("step"),
        "semantic_id": step.get("semantic_id"),
    }

    return cloned


def make_step_gated_occupy_action(
    action: Dict[str, Any],
    product_binding: Dict[str, Any],
    step_name: str,
    step: Dict[str, Any],
) -> Dict[str, Any]:
    cloned = copy.deepcopy(action)
    suffix = safe_id(step_name)
    cloned["key"] = f"{action['key']}__{suffix}" if suffix else f"{action['key']}__step"

    step_binding = {"kind": "object", "name": step_name}
    ready_atom = make_step_atom("step_ready", product_binding, step_binding)
    cloned.setdefault("preconditions", []).append(ready_atom)

    cloned["bop_step"] = {
        "name": step.get("name"),
        "order": step.get("step"),
        "semantic_id": step.get("semantic_id"),
        "gated_auxiliary": "occupy",
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
