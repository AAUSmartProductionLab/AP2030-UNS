from __future__ import annotations

from typing import Any, Dict, List, Optional

from .models import AIPlanningSource, _ParsedSource
from .utils import coerce_numeric_literal


def parse_source(source: AIPlanningSource) -> _ParsedSource:
    parsed = _ParsedSource(aas_id=source.aas_id, aas_name=source.aas_name or source.aas_id)

    top_elements = source.ai_planning_submodel.get("submodelElements", [])
    domain = find_collection(top_elements, "Domain")
    problem = find_collection(top_elements, "Problem")

    if problem:
        parse_problem(problem, parsed)
    else:
        parsed.warnings.append(f"{parsed.aas_name}: AIPlanning.Problem section missing.")

    source_objects = [obj["name"] for obj in parsed.objects]
    source_objects_full = list(parsed.objects)
    if domain:
        parse_domain(domain, parsed, source_objects, source_objects_full)
    else:
        parsed.warnings.append(f"{parsed.aas_name}: AIPlanning.Domain section missing.")

    return parsed


def parse_domain(domain: Dict[str, Any], parsed: _ParsedSource, source_objects: List[str], source_objects_full: Optional[List[Dict[str, Any]]] = None) -> None:
    domain_sections = domain.get("value", [])
    _sof = source_objects_full or []

    fluent_section = find_collection(domain_sections, "Fluents")
    if fluent_section:
        for fluent in fluent_section.get("value", []):
            parsed.fluents.append(parse_fluent(fluent, parsed.aas_name))

    action_section = find_collection(domain_sections, "Actions")
    if action_section:
        for action in action_section.get("value", []):
            parsed.actions.append(
                parse_action(action, parsed.aas_name, parsed.warnings, source_objects, action_kind="Action", source_objects_full=_sof)
            )

    process_section = find_collection(domain_sections, "Processes")
    if process_section:
        for process in process_section.get("value", []):
            parsed.actions.append(
                parse_action(process, parsed.aas_name, parsed.warnings, source_objects, action_kind="Process", source_objects_full=_sof)
            )

    event_section = find_collection(domain_sections, "Events")
    if event_section:
        for event in event_section.get("value", []):
            parsed.actions.append(
                parse_action(event, parsed.aas_name, parsed.warnings, source_objects, action_kind="Event", source_objects_full=_sof)
            )

    constraint_section = find_collection(domain_sections, "Constraints")
    if constraint_section is not None:
        parsed.constraints_terms.extend(parse_constraint_terms(constraint_section, parsed.aas_name, source_objects))


def parse_problem(problem: Dict[str, Any], parsed: _ParsedSource) -> None:
    sections = problem.get("value", [])

    objects_section = find_list(sections, "Objects")
    object_names: List[str] = []
    if objects_section:
        for obj in objects_section.get("value", []):
            name = display_name(obj) or f"Object_{len(object_names) + 1}"
            object_names.append(name)
            parsed.objects.append(
                {
                    "name": name,
                    "reference": reference_key_tail(obj.get("value")),
                    "declared_type": parameter_type_from_reference(obj.get("value")),
                    "source_aas_id": parsed.aas_id,
                    "source_aas_name": parsed.aas_name,
                }
            )

    init_section = find_collection(sections, "Init")
    if init_section:
        for term in init_section.get("value", []):
            node = parse_term(term, parsed.aas_name, object_names)
            if node is not None:
                parsed.init_terms.append(node)

    goal_section = find_collection(sections, "Goal")
    if goal_section:
        for term in goal_section.get("value", []):
            node = parse_term(term, parsed.aas_name, object_names)
            if node is not None:
                parsed.goal_terms.append(node)

    constraint_section = find_collection(sections, "Constraints")
    if constraint_section is not None:
        parsed.constraints_terms.extend(parse_constraint_terms(constraint_section, parsed.aas_name, object_names))

    if find_collection(sections, "Metric") is not None:
        parsed.warnings.append(
            f"{parsed.aas_name}: Problem.Metric present; ignored in v1 best-effort pipeline."
        )


def parse_fluent(fluent: Dict[str, Any], source_name: str) -> Dict[str, Any]:
    param_types: List[str] = []
    params_list = find_list(fluent.get("value", []), "Parameters")
    if params_list:
        for param in params_list.get("value", []):
            param_types.append(parameter_type_from_reference(param.get("value")))

    transformation = None
    value_type = "bool"
    for child in fluent.get("value", []):
        if child.get("modelType") == "Property" and child.get("idShort") == "Transformation":
            transformation = child.get("value")
        if child.get("modelType") == "Property" and child.get("idShort") == "Value":
            numeric_value = child.get("value")
            if coerce_numeric_literal(numeric_value) is not None:
                value_type = "numeric"

    return {
        "key": fluent.get("idShort") or display_name(fluent) or "Fluent",
        "semantic_id": first_semantic_id(fluent),
        "param_types": param_types,
        "transformation": transformation,
        "value_type": value_type,
        "source": source_name,
    }


def parse_action(
    action: Dict[str, Any],
    source_name: str,
    warnings: List[str],
    source_objects: List[str],
    action_kind: str,
    source_objects_full: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    values = action.get("value", [])

    action_key = action.get("idShort") or display_name(action) or "Action"
    skill_target = action_key

    skill_ref = find_reference(values, "SkillReference")
    if skill_ref is not None:
        skill_target = reference_key_tail(skill_ref.get("value")) or action_key

    parameters: List[Dict[str, Any]] = []
    params_list = find_list(values, "Parameters")
    if params_list:
        for idx, param in enumerate(params_list.get("value", [])):
            param_name = display_name(param) or f"p{idx}"
            param_ref = param.get("value")
            param_type = parameter_type_from_reference(param_ref)
            # Fallback: if a ModelReference resolved to a resource AAS type but the
            # parameter name clearly indicates a location, override to LocationParameter.
            if (
                param_type not in ("Entity", "LocationParameter")
                and param_name.lower().endswith("location")
            ):
                param_type = "LocationParameter"
            entry: Dict[str, Any] = {"name": param_name, "type": param_type}
            # Detect modelRef parameters whose value is already known from Problem.Objects
            # (i.e. the object is self or a property of self). These become constants in PDDL.
            if isinstance(param_ref, dict) and param_ref.get("type") == "ModelReference" and source_objects_full:
                ref_tail = reference_key_tail(param_ref)
                matched = next(
                    (obj for obj in source_objects_full if obj.get("reference") == ref_tail),
                    None,
                )
                if matched is not None:
                    entry["is_constant"] = True
                    entry["bound_object"] = matched["name"]
                else:
                    warnings.append(
                        f"{source_name}: ModelReference parameter '{param_name}' in action '{action_key}' "
                        f"has no matching Problem.Object (ref tail '{ref_tail}'); treated as free variable."
                    )
            parameters.append(entry)

    preconditions: List[Dict[str, Any]] = []
    effects: List[Dict[str, Any]] = []

    cond_section = find_collection(values, "Conditions")
    if cond_section:
        for group in cond_section.get("value", []):
            for term in group.get("value", []):
                node = parse_term(term, source_name, source_objects)
                if node is not None:
                    preconditions.append(node)

    eff_section = find_collection(values, "Effects")
    if eff_section:
        for group in eff_section.get("value", []):
            for term in group.get("value", []):
                node = parse_term(term, source_name, source_objects)
                if node is not None:
                    effects.append(node)

    if not preconditions:
        warnings.append(f"{source_name}: {action_kind} '{action_key}' has no parsed preconditions.")
    if not effects:
        warnings.append(f"{source_name}: {action_kind} '{action_key}' has no parsed effects.")

    action_semantic_ids = semantic_ids_from_item(action)

    return {
        "key": action_key,
        "semantic_id": action_semantic_ids[0] if action_semantic_ids else "",
        "semantic_ids": action_semantic_ids,
        "skill_target": skill_target,
        "parameters": parameters,
        "preconditions": preconditions,
        "effects": effects,
        "action_kind": action_kind,
        "source_name": source_name,
        "source_aas_id": "",
    }


def parse_constraint_terms(
    constraints_section: Dict[str, Any],
    source_name: str,
    source_objects: List[str],
) -> List[Dict[str, Any]]:
    parsed_terms: List[Dict[str, Any]] = []
    for term in constraints_section.get("value", []):
        node = parse_term(term, source_name, source_objects)
        if node is not None:
            parsed_terms.append(node)
    return parsed_terms


def parse_term(term: Dict[str, Any], source_name: str, source_objects: List[str]) -> Optional[Dict[str, Any]]:
    model_type = term.get("modelType")
    if model_type == "Property":
        return {
            "kind": "constant",
            "value": term.get("value"),
        }

    if model_type != "SubmodelElementCollection":
        return None

    values = term.get("value", [])
    fluent_ref = find_reference(values, "FluentReference")

    if fluent_ref is not None:
        fluent_key = fluent_key_from_reference(fluent_ref.get("value"))
        if not fluent_key:
            fluent_key = display_name(term) or semantic_tail(first_semantic_id(term)) or "Fluent"

        params: List[Dict[str, Any]] = []
        params_list = find_list(values, "Parameters")
        if params_list:
            for param in params_list.get("value", []):
                resolved = resolve_parameter_binding(param.get("value"), source_objects)
                if resolved is not None:
                    params.append(resolved)

        term_value = None
        for child in values:
            if child.get("modelType") == "Property" and child.get("idShort") == "Value":
                term_value = child.get("value")
                break

        atom = {
            "kind": "atom",
            "fluent": fluent_key,
            "params": params,
            "semantic_id": first_semantic_id(term),
        }
        if term_value is not None:
            atom["value"] = term_value
        return atom

    operator = term_operator(term)
    children: List[Dict[str, Any]] = []
    for child in values:
        if child.get("modelType") == "SubmodelElementCollection":
            parsed_child = parse_term(child, source_name, source_objects)
            if parsed_child is not None:
                children.append(parsed_child)
        elif child.get("modelType") == "Property" and str(child.get("idShort", "")).startswith("term_"):
            children.append(
                {
                    "kind": "constant",
                    "value": child.get("value"),
                }
            )

    if operator in {
        "not",
        "and",
        "or",
        "oneof",
        "+",
        "-",
        "*",
        "/",
        "=",
        "<",
        "<=",
        ">",
        ">=",
        "assign",
        "increase",
        "decrease",
        "scale-up",
        "scale-down",
        "always",
        "sometime",
        "at-most-once",
        "sometime-before",
        "sometime-after",
        "preferences",
        "preference",
    }:
        return {
            "kind": "op",
            "op": operator,
            "children": children,
        }

    if operator:
        return {
            "kind": "unsupported",
            "op": operator,
            "children": children,
        }

    return None


# Map lowered CSSx class-name tails to canonical PDDL operator strings.
_TAIL_TO_OPERATOR: Dict[str, str] = {
    # Arithmetic symbols
    "equal": "=",
    "lessthan": "<",
    "lessorequal": "<=",
    "greaterthan": ">",
    "greaterorequal": ">=",
    "add": "+",
    "subtract": "-",
    "multiply": "*",
    "divide": "/",
    # Hyphenated operators
    "scaleup": "scale-up",
    "scaledown": "scale-down",
    "atmostonce": "at-most-once",
    "sometimeafter": "sometime-after",
    "sometimebefore": "sometime-before",
    "alwayswithin": "always-within",
    "holdduring": "hold-during",
    "holdafter": "hold-after",
}


def term_operator(term: Dict[str, Any]) -> Optional[str]:
    for sid in term.get("supplementalSemanticIds", []):
        sem = semantic_from_ref(sid)
        tail = semantic_tail(sem).lower()
        tail = _TAIL_TO_OPERATOR.get(tail, tail)
        if tail in {"not", "and", "or"}:
            return tail
        if tail:
            return tail
    return None


def find_collection(items: List[Dict[str, Any]], id_short: str) -> Optional[Dict[str, Any]]:
    for item in items:
        if item.get("modelType") == "SubmodelElementCollection" and item.get("idShort") == id_short:
            return item
    return None


def find_list(items: List[Dict[str, Any]], id_short: str) -> Optional[Dict[str, Any]]:
    for item in items:
        if item.get("modelType") == "SubmodelElementList" and item.get("idShort") == id_short:
            return item
    return None


def find_reference(items: List[Dict[str, Any]], id_short: str) -> Optional[Dict[str, Any]]:
    for item in items:
        if item.get("modelType") == "ReferenceElement" and item.get("idShort") == id_short:
            return item
    return None


def display_name(item: Dict[str, Any]) -> str:
    display_name_entries = item.get("displayName", [])
    if isinstance(display_name_entries, list):
        for lang in display_name_entries:
            if isinstance(lang, dict) and str(lang.get("language", "")).startswith("en"):
                text = lang.get("text")
                if text:
                    return str(text)
        if display_name_entries and isinstance(display_name_entries[0], dict):
            return str(display_name_entries[0].get("text") or "")
    return str(item.get("idShort") or "")


def first_semantic_id(item: Dict[str, Any]) -> str:
    sem = item.get("semanticId")
    return semantic_from_ref(sem)


def semantic_ids_from_item(item: Dict[str, Any]) -> List[str]:
    semantic_ids: List[str] = []

    primary = first_semantic_id(item)
    if primary:
        semantic_ids.append(primary)

    for sid in item.get("supplementalSemanticIds", []):
        semantic_id = semantic_from_ref(sid)
        if semantic_id and semantic_id not in semantic_ids:
            semantic_ids.append(semantic_id)

    return semantic_ids


def semantic_from_ref(ref: Optional[Dict[str, Any]]) -> str:
    if not isinstance(ref, dict):
        return ""
    keys = ref.get("keys", [])
    if not keys:
        return ""
    return str(keys[0].get("value") or "")


def semantic_tail(semantic_id: str) -> str:
    if not semantic_id:
        return ""
    if "#" in semantic_id:
        return semantic_id.rsplit("#", 1)[-1]
    return semantic_id.rstrip("/").rsplit("/", 1)[-1]


def parameter_type_from_reference(reference: Optional[Dict[str, Any]]) -> str:
    if not isinstance(reference, dict):
        return "Entity"

    keys = reference.get("keys", [])
    if not keys:
        return "Entity"

    kind = str(reference.get("type") or "")
    tail = str(keys[-1].get("value") or "")
    if kind == "ExternalReference":
        return semantic_tail(tail) or "Entity"

    if kind == "ModelReference":
        # Location model refs (e.g. self/Parameters/Location) should type as LocationParameter,
        # not as the owning AAS resource type.
        location_like = {"location", "locationparameter"}
        for key in keys:
            value_tail = semantic_tail(str(key.get("value") or "")).lower()
            if value_tail in location_like:
                return "LocationParameter"

        aas_key = next((k for k in keys if str(k.get("type")) == "AssetAdministrationShell"), None)
        if aas_key is not None:
            aas_value = str(aas_key.get("value") or "")
            return semantic_tail(aas_value) or "Asset"
        return semantic_tail(tail) or "Asset"

    return "Entity"


def reference_key_tail(reference: Optional[Dict[str, Any]]) -> str:
    if not isinstance(reference, dict):
        return ""
    keys = reference.get("keys", [])
    if not keys:
        return ""
    return str(keys[-1].get("value") or "")


def fluent_key_from_reference(reference: Optional[Dict[str, Any]]) -> str:
    if not isinstance(reference, dict):
        return ""

    keys = reference.get("keys", [])
    if not keys:
        return ""

    values = [str(key.get("value") or "") for key in keys]
    if "Fluents" in values:
        idx = values.index("Fluents")
        if idx + 1 < len(values):
            return values[idx + 1]

    return semantic_tail(values[-1])


def resolve_parameter_binding(reference: Optional[Dict[str, Any]], source_objects: List[str]) -> Optional[Dict[str, Any]]:
    if not isinstance(reference, dict):
        return None

    keys = reference.get("keys", [])
    values = [str(key.get("value") or "") for key in keys]
    if not values:
        return None

    if "Problem" in values and "Objects" in values:
        index = last_reference_index(values)
        if index is not None and 0 <= index < len(source_objects):
            return {"kind": "object", "name": source_objects[index]}

    if "Constraints" in values and "Parameters" in values:
        index = last_reference_index(values)
        if index is not None and 0 <= index < len(source_objects):
            return {"kind": "object", "name": source_objects[index]}

    if "Parameters" in values:
        index = last_reference_index(values)
        if index is not None:
            return {"kind": "action_param", "index": index}

    if "Objects" in values:
        index = last_reference_index(values)
        if index is not None and 0 <= index < len(source_objects):
            return {"kind": "object", "name": source_objects[index]}

    tail = values[-1]
    if tail and tail not in {"Parameters", "Objects"}:
        return {"kind": "object", "name": semantic_tail(tail) or tail}

    return None


def last_reference_index(values: List[str]) -> Optional[int]:
    for value in reversed(values):
        if value.isdigit():
            return int(value)
    return None
