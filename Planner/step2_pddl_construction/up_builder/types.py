from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..utils import safe_id

ACTIVE_TYPE_PARENTS: Dict[str, str] = {}

ROOT_TYPE_NAME = "Thing"
_ROOT_TYPE_ALIASES = {
    "thing",
    "entity",
    "owl:thing",
    "http://www.w3.org/2002/07/owl#thing",
}

def canonical_type_name(type_name: Any) -> str:
    raw = str(type_name or "").strip()
    if not raw:
        return ROOT_TYPE_NAME
    if raw.lower() in _ROOT_TYPE_ALIASES:
        return ROOT_TYPE_NAME
    return raw


def normalize_type_parent_map(type_parents: Dict[str, str]) -> Dict[str, str]:
    normalized: Dict[str, str] = {}
    for child, parent in type_parents.items():
        child_name = canonical_type_name(child)
        parent_name = canonical_type_name(parent)
        if child_name == ROOT_TYPE_NAME or child_name == parent_name:
            continue
        normalized.setdefault(child_name, parent_name)
    return normalized

def collect_type_names(merged: Dict[str, Any]) -> List[str]:
    type_names = {ROOT_TYPE_NAME}

    for fluent in merged.get("fluents", []):
        for ptype in fluent.get("param_types", []):
            type_names.add(canonical_type_name(ptype))

    for action in merged.get("actions", []):
        for parameter in action.get("parameters", []):
            type_names.add(canonical_type_name(parameter.get("type")))

    for obj in merged.get("objects", []):
        type_names.add(canonical_type_name(obj.get("declared_type")))

    return sorted(type_names)


def build_type_map(
    type_names: List[str],
    type_parents: Dict[str, str],
    user_type_ctor: Any,
    warnings: List[str],
) -> Dict[str, Any]:
    root_type = user_type_ctor(ROOT_TYPE_NAME)
    type_map: Dict[str, Any] = {
        ROOT_TYPE_NAME: root_type,
        "Entity": root_type,
        "owl:Thing": root_type,
    }
    used_ids = {ROOT_TYPE_NAME}

    pending = [
        canonical_type_name(type_name)
        for type_name in type_names
        if canonical_type_name(type_name) != ROOT_TYPE_NAME
    ]
    pending = [type_name for type_name in pending if type_name not in type_map]

    while pending:
        progressed = False
        for type_name in list(pending):
            parent_name = canonical_type_name(type_parents.get(type_name, ROOT_TYPE_NAME))
            if parent_name != ROOT_TYPE_NAME and parent_name not in type_map and parent_name in pending:
                continue

            parent_type = type_map.get(parent_name, root_type)
            if parent_name not in type_map and parent_name != ROOT_TYPE_NAME:
                warnings.append(
                    f"Unknown parent type '{parent_name}' for '{type_name}'; attaching to {ROOT_TYPE_NAME}."
                )

            base_id = safe_id(type_name) or "Type"
            type_id = base_id
            suffix = 2
            while type_id in used_ids:
                type_id = f"{base_id}_{suffix}"
                suffix += 1

            used_ids.add(type_id)
            type_map[type_name] = user_type_ctor(type_id, father=parent_type)
            pending.remove(type_name)
            progressed = True

        if progressed:
            continue

        for type_name in list(pending):
            base_id = safe_id(type_name) or "Type"
            type_id = base_id
            suffix = 2
            while type_id in used_ids:
                type_id = f"{base_id}_{suffix}"
                suffix += 1

            warnings.append(f"Type hierarchy cycle detected for '{type_name}'; attaching to {ROOT_TYPE_NAME}.")
            used_ids.add(type_id)
            type_map[type_name] = user_type_ctor(type_id, father=root_type)
            pending.remove(type_name)

    return type_map


def infer_type_parent_map(
    merged: Dict[str, Any],
    warnings: List[str],
    known_parents: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    fluent_types = {
        str(fluent.get("key") or ""): [canonical_type_name(t) for t in fluent.get("param_types", [])]
        for fluent in merged.get("fluents", [])
    }
    object_types = {
        str(obj.get("name") or ""): canonical_type_name(obj.get("declared_type"))
        for obj in merged.get("objects", [])
    }

    parent_map: Dict[str, str] = {}

    def _is_ancestor(candidate_ancestor: str, candidate_descendant: str) -> bool:
        """Return True if *candidate_ancestor* is a (transitive) parent of
        *candidate_descendant* according to the loaded ontology / known type
        hierarchy.  Used to prefer the more-specific type on conflicts."""
        if not known_parents:
            return False
        seen: set[str] = set()
        cursor = canonical_type_name(candidate_descendant)
        while cursor in known_parents and cursor not in seen:
            seen.add(cursor)
            cursor = canonical_type_name(known_parents[cursor])
            if cursor == candidate_ancestor:
                return True
        return False

    def register_parent(child: str, parent: str, context: str) -> None:
        child_t = canonical_type_name(child)
        parent_t = canonical_type_name(parent)

        # Product/resource AAS shell types (e.g. MIM8AAS, planarTableShuttle1AAS)
        # should not become parents of generic semantic classes from predicates.
        if child_t in {"Product", "Resource", "Transport", "LocationParameter"} and parent_t.endswith("AAS"):
            return

        # If a specific AAS shell type is observed where a semantic class is expected,
        # keep the semantic class as the parent, not vice versa.
        if child_t.endswith("AAS") and parent_t in {"Product", "Resource", "Transport", "LocationParameter"}:
            pass

        if child_t == ROOT_TYPE_NAME or parent_t == ROOT_TYPE_NAME or child_t == parent_t:
            return

        # Reject back-edges against the loaded ontology: if parent_t is already
        # a transitive descendant of child_t in known_parents, registering
        # child_t → parent_t would create a cycle (e.g. an AAS author typing
        # a station argument as Resource where the predicate expects CPPM
        # would otherwise infer Resource → CPPM, contradicting CPPM → Resource).
        if _is_ancestor(child_t, parent_t):
            warnings.append(
                f"Skipping inferred parent '{child_t}' → '{parent_t}' from {context}: "
                f"'{parent_t}' is already a descendant of '{child_t}' in the ontology."
            )
            return

        existing_parent = parent_map.get(child_t)
        if existing_parent is None:
            parent_map[child_t] = parent_t
            return

        if existing_parent != parent_t:
            # When both proposed parents sit on the same ancestry chain,
            # keep the more-specific (descendant) type.
            if _is_ancestor(existing_parent, parent_t):
                # parent_t is more specific → replace
                parent_map[child_t] = parent_t
                return
            if _is_ancestor(parent_t, existing_parent):
                # existing_parent is already more specific → keep it
                return
            warnings.append(
                f"Type parent conflict for '{child_t}' in {context}: keeping '{existing_parent}', ignoring '{parent_t}'."
            )

    def walk_term(term: Dict[str, Any], action_param_types: Optional[List[str]], context: str) -> None:
        if term.get("kind") == "atom":
            fluent_name = str(term.get("fluent") or "")
            expected_types = fluent_types.get(fluent_name, [])

            for idx, binding in enumerate(term.get("params", [])):
                expected_type = expected_types[idx] if idx < len(expected_types) else ROOT_TYPE_NAME
                if binding.get("kind") == "action_param" and action_param_types is not None:
                    action_idx = int(binding.get("index", -1))
                    if 0 <= action_idx < len(action_param_types):
                        register_parent(action_param_types[action_idx], expected_type, context)
                elif binding.get("kind") == "object":
                    obj_name = str(binding.get("name") or "")
                    actual_type = object_types.get(obj_name, ROOT_TYPE_NAME)
                    register_parent(actual_type, expected_type, context)
            return

        for child in term.get("children", []):
            walk_term(child, action_param_types, context)

    for action in merged.get("actions", []):
        action_param_types = [canonical_type_name(param.get("type")) for param in action.get("parameters", [])]
        context = f"action '{action.get('key')}'"
        for term in action.get("preconditions", []):
            walk_term(term, action_param_types, context)
        for term in action.get("effects", []):
            walk_term(term, action_param_types, context)

    for term in merged.get("init_terms", []):
        walk_term(term, None, "init")
    for term in merged.get("goal_terms", []):
        walk_term(term, None, "goal")
    for term in merged.get("constraints_terms", []):
        walk_term(term, None, "constraint")

    # Source-provenance inference: when a resource AAS declares both an object
    # (typed by its AAS id, e.g. "planarTableShuttle1AAS") and actions whose
    # first parameter uses a semantic role type (e.g. "Transport"), infer that
    # the AAS-specific object type IS-A the semantic role type.  This connects
    # e.g. planarTableShuttle1AAS → Transport in the type hierarchy.
    source_obj_types: Dict[str, set] = {}
    for obj in merged.get("objects", []):
        src = canonical_type_name(obj.get("source_aas_name") or "")
        obj_type = canonical_type_name(obj.get("declared_type"))
        if src and obj_type:
            source_obj_types.setdefault(src, set()).add(obj_type)

    for action in merged.get("actions", []):
        sources_list = action.get("sources") or []
        if not sources_list:
            src_name = action.get("source_name", "")
            src_id = action.get("source_aas_id", "")
            if src_name:
                sources_list = [(src_id, src_name)]

        params = action.get("parameters", [])
        if not params:
            continue
        self_param_type = canonical_type_name(params[0].get("type"))
        if not self_param_type or self_param_type == ROOT_TYPE_NAME:
            continue

        for _, src_name in sources_list:
            src_name_c = canonical_type_name(src_name)
            for obj_type in source_obj_types.get(src_name_c, ()):
                if obj_type == src_name_c and obj_type != self_param_type:
                    register_parent(obj_type, self_param_type,
                                    f"source provenance (action '{action.get('key')}' from '{src_name}')")

    return parent_map



def types_compatible(actual_type: str, expected_type: str) -> bool:
    actual = canonical_type_name(actual_type)
    expected = canonical_type_name(expected_type)
    if expected == ROOT_TYPE_NAME:
        return True
    if actual == expected:
        return True

    seen: set[str] = set()
    cursor = actual
    while cursor in ACTIVE_TYPE_PARENTS and cursor not in seen:
        seen.add(cursor)
        cursor = ACTIVE_TYPE_PARENTS[cursor]
        if cursor == expected:
            return True
    return False
