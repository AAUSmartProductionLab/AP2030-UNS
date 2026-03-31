from __future__ import annotations

import json
from typing import Any, Dict, List

from ai_pipeline.models import _ParsedSource
from ai_pipeline.utils import safe_id


def merge_sources(parsed_sources: List[_ParsedSource], warnings: List[str]) -> Dict[str, Any]:
    merged: Dict[str, Any] = {
        "fluents": [],
        "actions": [],
        "objects": [],
        "init_terms": [],
        "goal_terms": [],
        "constraints_terms": [],
        "source_lookup": {},
    }

    fluent_by_key: Dict[str, Dict[str, Any]] = {}
    action_by_key: Dict[str, Dict[str, Any]] = {}
    object_by_name: Dict[str, Dict[str, Any]] = {}

    for source in parsed_sources:
        merged["source_lookup"][source.aas_id] = source.aas_name

        object_name_map: Dict[str, str] = {}
        for obj in source.objects:
            name = obj["name"]
            if name not in object_by_name:
                object_by_name[name] = dict(obj)
                merged["objects"].append(object_by_name[name])
                object_name_map[name] = name
                continue

            existing = object_by_name[name]
            if existing.get("reference") == obj.get("reference"):
                object_name_map[name] = name
                continue

            namespaced = namespace_name(source.aas_name, name)
            warnings.append(
                f"Object '{name}' from {source.aas_name} conflicted; namespaced to '{namespaced}'."
            )
            namespaced_obj = dict(obj)
            namespaced_obj["name"] = namespaced
            object_by_name[namespaced] = namespaced_obj
            merged["objects"].append(namespaced_obj)
            object_name_map[name] = namespaced

        fluent_name_map: Dict[str, str] = {}
        for fluent in source.fluents:
            key = fluent["key"]
            signature = (key.lower(), tuple(fluent["param_types"]))
            if key not in fluent_by_key:
                entry = dict(fluent)
                entry["signature"] = signature
                fluent_by_key[key] = entry
                merged["fluents"].append(entry)
                fluent_name_map[key] = key
                continue

            existing = fluent_by_key[key]
            if existing["signature"] == signature:
                fluent_name_map[key] = key
                continue

            namespaced = namespace_name(source.aas_name, key)
            fluent_name_map[key] = namespaced
            warnings.append(
                f"Fluent '{key}' from {source.aas_name} conflicted; namespaced to '{namespaced}'."
            )
            entry = dict(fluent)
            entry["key"] = namespaced
            entry["signature"] = (namespaced.lower(), tuple(fluent["param_types"]))
            fluent_by_key[namespaced] = entry
            merged["fluents"].append(entry)

        for action in source.actions:
            remapped_action = remap_action_fluents(action, fluent_name_map)
            remapped_action["source_aas_id"] = source.aas_id
            remapped_action["source_name"] = source.aas_name
            key = remapped_action["key"]

            if key not in action_by_key:
                remapped_action["sources"] = [(source.aas_id, source.aas_name)]
                remapped_action["fingerprint"] = action_fingerprint(remapped_action)
                action_by_key[key] = remapped_action
                merged["actions"].append(remapped_action)
                continue

            existing = action_by_key[key]
            new_fp = action_fingerprint(remapped_action)
            if existing["fingerprint"] == new_fp:
                existing["sources"].append((source.aas_id, source.aas_name))
                continue

            namespaced = namespace_name(source.aas_name, key)
            warnings.append(
                f"Action '{key}' from {source.aas_name} conflicted; namespaced to '{namespaced}'."
            )
            remapped_action["key"] = namespaced
            remapped_action["sources"] = [(source.aas_id, source.aas_name)]
            remapped_action["fingerprint"] = action_fingerprint(remapped_action)
            action_by_key[namespaced] = remapped_action
            merged["actions"].append(remapped_action)

        merged["init_terms"].extend(remap_problem_terms(source.init_terms, fluent_name_map, object_name_map))
        merged["goal_terms"].extend(remap_problem_terms(source.goal_terms, fluent_name_map, object_name_map))
        merged["constraints_terms"].extend(
            remap_problem_terms(source.constraints_terms, fluent_name_map, object_name_map)
        )

    return merged


def remap_action_fluents(action: Dict[str, Any], fluent_name_map: Dict[str, str]) -> Dict[str, Any]:
    cloned = json.loads(json.dumps(action))
    cloned["preconditions"] = remap_terms(cloned["preconditions"], fluent_name_map)
    cloned["effects"] = remap_terms(cloned["effects"], fluent_name_map)
    return cloned


def remap_problem_terms(
    terms: List[Dict[str, Any]],
    fluent_name_map: Dict[str, str],
    object_name_map: Dict[str, str],
) -> List[Dict[str, Any]]:
    remapped = remap_terms(terms, fluent_name_map)
    for term in remapped:
        remap_term_objects(term, object_name_map)
    return remapped


def remap_terms(terms: List[Dict[str, Any]], fluent_name_map: Dict[str, str]) -> List[Dict[str, Any]]:
    result = []
    for term in terms:
        cloned = json.loads(json.dumps(term))
        remap_term_fluent(cloned, fluent_name_map)
        result.append(cloned)
    return result


def remap_term_fluent(term: Dict[str, Any], fluent_name_map: Dict[str, str]) -> None:
    if term.get("kind") == "atom":
        fluent = term.get("fluent")
        if fluent in fluent_name_map:
            term["fluent"] = fluent_name_map[fluent]
        return

    for child in term.get("children", []):
        remap_term_fluent(child, fluent_name_map)


def remap_term_objects(term: Dict[str, Any], object_name_map: Dict[str, str]) -> None:
    if term.get("kind") == "atom":
        for param in term.get("params", []):
            if param.get("kind") == "object":
                name = param.get("name")
                if name in object_name_map:
                    param["name"] = object_name_map[name]
        return

    for child in term.get("children", []):
        remap_term_objects(child, object_name_map)


def action_fingerprint(action: Dict[str, Any]) -> str:
    comparable = {
        "action_kind": action.get("action_kind"),
        "skill_target": action.get("skill_target"),
        "parameters": action.get("parameters"),
        "preconditions": action.get("preconditions"),
        "effects": action.get("effects"),
    }
    return json.dumps(comparable, sort_keys=True)


def namespace_name(source: str, key: str) -> str:
    return f"{safe_id(source)}__{safe_id(key)}"
