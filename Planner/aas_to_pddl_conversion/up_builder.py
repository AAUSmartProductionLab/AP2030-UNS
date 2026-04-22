from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .models import PlanningCapability
from .ontology_resolver import load_type_parent_map
from .utils import coerce_numeric_literal, safe_id


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


def build_up_problem(
    merged: Dict[str, Any],
    warnings: List[str],
    semantic_natural_transitions: bool = True,
    drop_natural_transitions: bool = False,
    include_trajectory_constraints: bool = True,
) -> Any:
    from unified_planning.model import Event, Process
    from unified_planning.shortcuts import (
        Always,
        And,
        AtMostOnce,
        BoolType,
        InstantaneousAction,
        Not,
        Or,
        Problem,
        RealType,
        Sometime,
        SometimeAfter,
        SometimeBefore,
        UserType,
    )

    problem = Problem("merged_ai_planning")
    all_type_names = collect_type_names(merged)
    loaded_type_parents = load_type_parent_map(warnings=warnings)
    inferred_type_parents = normalize_type_parent_map(
        infer_type_parent_map(merged, warnings, known_parents=loaded_type_parents)
    )
    if loaded_type_parents is None:
        type_parents = inferred_type_parents
    else:
        type_parents = normalize_type_parent_map(loaded_type_parents)
        for child, parent in inferred_type_parents.items():
            type_parents.setdefault(child, parent)

    # Normalize common CSS/CSSX aliases so semantic references and inferred AAS types align.
    # This keeps compatibility with externalRef values like css:Resource/css:Product.
    type_parents.setdefault("Resource", ROOT_TYPE_NAME)
    type_parents.setdefault("Product", ROOT_TYPE_NAME)
    type_parents.setdefault("Transport", "Resource")
    type_parents.setdefault("LocationParameter", ROOT_TYPE_NAME)
    type_parents.setdefault("MIM8AAS", "Product")

    # Ensure intermediate ontology types (e.g. CPS between Transport and Resource)
    # are present so build_type_map can construct the full chain.
    type_name_set = set(all_type_names)
    for child, parent in type_parents.items():
        if child not in type_name_set:
            all_type_names.append(child)
            type_name_set.add(child)
        if parent != ROOT_TYPE_NAME and parent not in type_name_set:
            all_type_names.append(parent)
            type_name_set.add(parent)

    type_map = build_type_map(all_type_names, type_parents, UserType, warnings)
    global ACTIVE_TYPE_PARENTS
    ACTIVE_TYPE_PARENTS = dict(type_parents)
    root_type = type_map[ROOT_TYPE_NAME]
    warnings.append("Type constraints are enforced from AAS parameter declarations where available.")

    fluent_map: Dict[str, Any] = {}
    fluent_param_types: Dict[str, List[str]] = {}
    for fluent in merged["fluents"]:
        key = safe_id(fluent["key"])
        if not key:
            continue

        param_names = [f"p{i}" for i, _ in enumerate(fluent["param_types"])]
        params = {
            name: type_map.get(canonical_type_name(fluent["param_types"][idx]), root_type)
            for idx, name in enumerate(param_names)
        }
        if str(fluent.get("value_type") or "bool") == "numeric":
            fluent_obj = problem.add_fluent(key, RealType(), default_initial_value=0.0, **params)
        else:
            fluent_obj = problem.add_fluent(key, BoolType(), default_initial_value=False, **params)
        fluent_map[fluent["key"]] = fluent_obj
        fluent_param_types[fluent["key"]] = [canonical_type_name(t) for t in fluent["param_types"]]

    for missing_name, arity in collect_missing_fluents(merged, fluent_map).items():
        safe_name = safe_id(missing_name)
        param_names = [f"p{i}" for i in range(arity)]
        params = {name: root_type for name in param_names}
        fluent_obj = problem.add_fluent(safe_name, BoolType(), default_initial_value=False, **params)
        fluent_map[missing_name] = fluent_obj
        fluent_param_types[missing_name] = [ROOT_TYPE_NAME] * arity
        warnings.append(
            f"Fluent '{missing_name}' was referenced but not declared in Domain.Fluents; auto-declared with arity {arity}."
        )

    object_map: Dict[str, Any] = {}
    object_types: Dict[str, str] = {}
    for obj in merged["objects"]:
        safe_name = safe_id(obj["name"])
        if not safe_name:
            continue
        if obj["name"] in object_map:
            continue

        declared_type = canonical_type_name(obj.get("declared_type"))
        up_type = type_map.get(declared_type, root_type)
        up_obj = problem.add_object(safe_name, up_type)
        object_map[obj["name"]] = up_obj
        object_map[safe_name] = up_obj
        object_types[obj["name"]] = declared_type
        object_types[safe_name] = declared_type

    transition_name_use: Dict[str, int] = {}
    for action in merged["actions"]:
        desired_name = safe_id(action.get("skill_target") or action["key"]) or safe_id(action["key"])
        if desired_name in transition_name_use:
            transition_name_use[desired_name] += 1
            desired_name = f"{desired_name}_{transition_name_use[desired_name]}"
        else:
            transition_name_use[desired_name] = 1

        action_param_types = [canonical_type_name(param.get("type")) for param in action["parameters"]]

        # Build param_remap: maps each original parameter index to either a free UP
        # variable name or a ground constant object name. Parameters declared via
        # modelRef that have a matching Problem.Object are constants; all others are free.
        param_remap: Dict[int, Dict[str, Any]] = {}
        free_param_types: List[str] = []
        for orig_idx, param in enumerate(action["parameters"]):
            if param.get("is_constant") and param.get("bound_object"):
                param_remap[orig_idx] = {"kind": "constant", "object_name": param["bound_object"]}
            else:
                free_idx = len(free_param_types)
                param_remap[orig_idx] = {"kind": "free", "up_param": f"p{free_idx}"}
                free_param_types.append(action_param_types[orig_idx])

        params = {
            f"p{i}": type_map.get(free_param_types[i], root_type)
            for i in range(len(free_param_types))
        }
        action_kind = str(action.get("action_kind") or "Action")

        if action_kind == "Action":
            up_action = InstantaneousAction(desired_name, **params)

            for term in action["preconditions"]:
                expr = term_to_condition(
                    term,
                    fluent_map,
                    fluent_param_types,
                    up_action,
                    action_param_types,
                    object_map,
                    object_types,
                    And,
                    Or,
                    Not,
                    warnings,
                    param_remap=param_remap,
                )
                if expr is not None:
                    up_action.add_precondition(expr)

            for term in action["effects"]:
                add_effects_from_term(
                    term,
                    up_action,
                    action_param_types,
                    fluent_map,
                    fluent_param_types,
                    object_map,
                    object_types,
                    warnings,
                    param_remap=param_remap,
                )

            problem.add_action(up_action)
            continue

        if drop_natural_transitions and action_kind in {"Event", "Process"}:
            continue

        if not semantic_natural_transitions and action_kind in {"Event", "Process"}:
            up_action = InstantaneousAction(desired_name, **params)

            for term in action["preconditions"]:
                expr = term_to_condition(
                    term,
                    fluent_map,
                    fluent_param_types,
                    up_action,
                    action_param_types,
                    object_map,
                    object_types,
                    And,
                    Or,
                    Not,
                    warnings,
                    param_remap=param_remap,
                )
                if expr is not None:
                    up_action.add_precondition(expr)

            for term in action["effects"]:
                add_effects_from_term(
                    term,
                    up_action,
                    action_param_types,
                    fluent_map,
                    fluent_param_types,
                    object_map,
                    object_types,
                    warnings,
                    param_remap=param_remap,
                )

            problem.add_action(up_action)
            warnings.append(
                f"{action_kind} '{action.get('key')}' lowered to action in solver-compatible approximation mode."
            )
            continue

        if action_kind == "Event":
            up_event = Event(desired_name, **params)

            for term in action["preconditions"]:
                expr = term_to_condition(
                    term,
                    fluent_map,
                    fluent_param_types,
                    up_event,
                    action_param_types,
                    object_map,
                    object_types,
                    And,
                    Or,
                    Not,
                    warnings,
                    param_remap=param_remap,
                )
                if expr is not None:
                    up_event.add_precondition(expr)

            for term in action["effects"]:
                add_effects_from_term(
                    term,
                    up_event,
                    action_param_types,
                    fluent_map,
                    fluent_param_types,
                    object_map,
                    object_types,
                    warnings,
                    param_remap=param_remap,
                )

            problem.add_event(up_event)
            continue

        if action_kind == "Process":
            up_process = Process(desired_name, **params)

            for term in action["preconditions"]:
                expr = term_to_condition(
                    term,
                    fluent_map,
                    fluent_param_types,
                    up_process,
                    action_param_types,
                    object_map,
                    object_types,
                    And,
                    Or,
                    Not,
                    warnings,
                    param_remap=param_remap,
                )
                if expr is not None:
                    up_process.add_precondition(expr)

            process_supported = True
            for term in action["effects"]:
                if not add_process_effects_from_term(
                    term,
                    up_process,
                    action_param_types,
                    fluent_map,
                    fluent_param_types,
                    object_map,
                    object_types,
                    warnings,
                    param_remap=param_remap,
                ):
                    process_supported = False
                    break

            if process_supported and len(up_process.effects) > 0:
                problem.add_process(up_process)
            else:
                raise ValueError(
                    f"Process '{action.get('key')}' has invalid continuous effects; expected increase/decrease over numeric fluents."
                )
            continue

        warnings.append(
            f"Unknown action kind '{action_kind}' for '{action.get('key')}'; lowering as action."
        )
        fallback_action = InstantaneousAction(desired_name, **params)
        for term in action["preconditions"]:
            expr = term_to_condition(
                term,
                fluent_map,
                fluent_param_types,
                fallback_action,
                action_param_types,
                object_map,
                object_types,
                And,
                Or,
                Not,
                warnings,
                param_remap=param_remap,
            )
            if expr is not None:
                fallback_action.add_precondition(expr)
        for term in action["effects"]:
            add_effects_from_term(
                term,
                fallback_action,
                action_param_types,
                fluent_map,
                fluent_param_types,
                object_map,
                object_types,
                warnings,
                param_remap=param_remap,
            )
        problem.add_action(fallback_action)

    for term in merged["init_terms"]:
        apply_init_term(problem, term, fluent_map, fluent_param_types, object_map, object_types, warnings)

    for term in merged["goal_terms"]:
        expr = term_to_goal(
            term,
            fluent_map,
            fluent_param_types,
            object_map,
            object_types,
            And,
            Or,
            Not,
            warnings,
        )
        if expr is not None:
            problem.add_goal(expr)

    if include_trajectory_constraints:
        for term in merged.get("constraints_terms", []):
            apply_trajectory_constraint(
                problem,
                term,
                fluent_map,
                fluent_param_types,
                object_map,
                object_types,
                And,
                Or,
                Not,
                Always,
                Sometime,
                AtMostOnce,
                SometimeBefore,
                SometimeAfter,
                warnings,
            )

    return problem


def add_process_effects_from_term(
    term: Dict[str, Any],
    process: Any,
    action_param_types: List[str],
    fluent_map: Dict[str, Any],
    fluent_param_types: Dict[str, List[str]],
    object_map: Dict[str, Any],
    object_types: Dict[str, str],
    warnings: List[str],
    param_remap: Optional[Dict[int, Dict[str, Any]]] = None,
) -> bool:
    kind = term.get("kind")

    if kind == "op" and term.get("op") == "and":
        ok = True
        for child in term.get("children", []):
            ok = add_process_effects_from_term(
                child,
                process,
                action_param_types,
                fluent_map,
                fluent_param_types,
                object_map,
                object_types,
                warnings,
                param_remap=param_remap,
            ) and ok
        return ok

    if kind == "op" and term.get("op") in {"increase", "decrease"}:
        children = term.get("children", [])
        if len(children) != 2:
            raise ValueError(
                f"Process '{getattr(process, 'name', 'process')}' effect '{term.get('op')}' requires exactly two terms."
            )

        target_expr = term_to_atom(
            children[0],
            fluent_map,
            fluent_param_types,
            process,
            action_param_types,
            object_map,
            object_types,
            warnings,
            param_remap=param_remap,
        )
        if target_expr is None:
            raise ValueError(
                f"Process '{getattr(process, 'name', 'process')}' has an invalid continuous effect target."
            )

        delta_expr = term_to_numeric_expression(
            children[1],
            process,
            action_param_types,
            fluent_map,
            fluent_param_types,
            object_map,
            object_types,
            warnings,
            param_remap=param_remap,
        )

        if term.get("op") == "increase":
            process.add_increase_continuous_effect(target_expr, delta_expr)
        else:
            process.add_decrease_continuous_effect(target_expr, delta_expr)
        return True

    raise ValueError(
        f"Process '{getattr(process, 'name', 'process')}' has unsupported effect term '{kind}:{term.get('op')}'. "
        "Only conjunctions and increase/decrease continuous effects are supported."
    )


def term_to_numeric_expression(
    term: Dict[str, Any],
    action: Any,
    action_param_types: List[str],
    fluent_map: Dict[str, Any],
    fluent_param_types: Dict[str, List[str]],
    object_map: Dict[str, Any],
    object_types: Dict[str, str],
    warnings: List[str],
    param_remap: Optional[Dict[int, Dict[str, Any]]] = None,
) -> Any:
    kind = term.get("kind")

    if kind == "constant":
        value = term.get("value")
        numeric_value = coerce_numeric_literal(value)
        if numeric_value is not None:
            return numeric_value
        raise ValueError(f"Numeric expression constant must be int/float, got '{value}'.")

    if kind == "atom":
        expr = term_to_atom(
            term,
            fluent_map,
            fluent_param_types,
            action,
            action_param_types,
            object_map,
            object_types,
            warnings,
            param_remap=param_remap,
        )
        if expr is None:
            raise ValueError("Numeric expression fluent term could not be resolved.")
        return expr

    if kind == "op":
        op = str(term.get("op") or "")
        children = term.get("children", [])

        if op in {"+", "-", "*", "/"}:
            if len(children) != 2:
                raise ValueError(f"Numeric operator '{op}' requires exactly two arguments.")

            left = term_to_numeric_expression(
                children[0],
                action,
                action_param_types,
                fluent_map,
                fluent_param_types,
                object_map,
                object_types,
                warnings,
                param_remap=param_remap,
            )
            right = term_to_numeric_expression(
                children[1],
                action,
                action_param_types,
                fluent_map,
                fluent_param_types,
                object_map,
                object_types,
                warnings,
                param_remap=param_remap,
            )

            if op == "+":
                return left + right
            if op == "-":
                return left - right
            if op == "*":
                return left * right
            return left / right

    raise ValueError(f"Unsupported numeric expression term '{kind}:{term.get('op')}'.")


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


def build_capabilities(merged: Dict[str, Any]) -> List[PlanningCapability]:
    capabilities: List[PlanningCapability] = []

    for action in merged["actions"]:
        if str(action.get("action_kind") or "Action") != "Action":
            continue

        name = action.get("skill_target") or action["key"]
        semantic_id = action.get("semantic_id") or f"http://www.w3id.org/aau-ra/cssx#{name}Capability"

        resources: Dict[str, str] = {}
        for aas_id, aas_name in action.get("sources", []):
            resources[aas_name] = aas_id

        capabilities.append(
            PlanningCapability(
                name=name,
                semantic_id=semantic_id,
                resources=resources,
            )
        )

    return capabilities


def collect_missing_fluents(merged: Dict[str, Any], fluent_map: Dict[str, Any]) -> Dict[str, int]:
    missing: Dict[str, int] = {}
    known = set(fluent_map.keys())

    term_lists = [
        merged.get("init_terms", []),
        merged.get("goal_terms", []),
    ]
    for action in merged.get("actions", []):
        term_lists.append(action.get("preconditions", []))
        term_lists.append(action.get("effects", []))
    term_lists.append(merged.get("constraints_terms", []))

    for terms in term_lists:
        for term in terms:
            accumulate_missing_fluents(term, known, missing)

    return missing


def accumulate_missing_fluents(term: Dict[str, Any], known: set[str], missing: Dict[str, int]) -> None:
    if term.get("kind") == "atom":
        name = str(term.get("fluent") or "")
        if name and name not in known:
            arity = len(term.get("params", []))
            previous = missing.get(name)
            if previous is None or arity > previous:
                missing[name] = arity
        return

    for child in term.get("children", []):
        accumulate_missing_fluents(child, known, missing)


def term_to_condition(
    term: Dict[str, Any],
    fluent_map: Dict[str, Any],
    fluent_param_types: Dict[str, List[str]],
    action: Any,
    action_param_types: List[str],
    object_map: Dict[str, Any],
    object_types: Dict[str, str],
    And: Any,
    Or: Any,
    Not: Any,
    warnings: List[str],
    param_remap: Optional[Dict[int, Dict[str, Any]]] = None,
) -> Any:
    kind = term.get("kind")
    if kind == "unsupported":
        warnings.append(f"Unsupported precondition operator '{term.get('op')}' ignored.")
        return None

    if kind == "atom":
        atom = term_to_atom(
            term,
            fluent_map,
            fluent_param_types,
            action,
            action_param_types,
            object_map,
            object_types,
            warnings,
            param_remap=param_remap,
        )
        return atom

    if kind == "op":
        op = term.get("op")
        children = [
            term_to_condition(
                child,
                fluent_map,
                fluent_param_types,
                action,
                action_param_types,
                object_map,
                object_types,
                And,
                Or,
                Not,
                warnings,
                param_remap=param_remap,
            )
            for child in term.get("children", [])
        ]
        children = [child for child in children if child is not None]
        if not children:
            return None

        if op == "not":
            return Not(children[0])
        if op == "and":
            return And(*children)
        if op == "or":
            return Or(*children)

    return None


def term_to_goal(
    term: Dict[str, Any],
    fluent_map: Dict[str, Any],
    fluent_param_types: Dict[str, List[str]],
    object_map: Dict[str, Any],
    object_types: Dict[str, str],
    And: Any,
    Or: Any,
    Not: Any,
    warnings: List[str],
) -> Any:
    kind = term.get("kind")
    if kind == "unsupported":
        warnings.append(f"Unsupported goal operator '{term.get('op')}' ignored.")
        return None

    if kind == "atom":
        return term_to_atom(
            term,
            fluent_map,
            fluent_param_types,
            None,
            [],
            object_map,
            object_types,
            warnings,
        )

    if kind == "op":
        op = term.get("op")
        children = [
            term_to_goal(
                child,
                fluent_map,
                fluent_param_types,
                object_map,
                object_types,
                And,
                Or,
                Not,
                warnings,
            )
            for child in term.get("children", [])
        ]
        children = [child for child in children if child is not None]
        if not children:
            return None

        if op == "not":
            return Not(children[0])
        if op == "and":
            return And(*children)
        if op == "or":
            return Or(*children)

    return None


def term_to_atom(
    term: Dict[str, Any],
    fluent_map: Dict[str, Any],
    fluent_param_types: Dict[str, List[str]],
    action: Any,
    action_param_types: List[str],
    object_map: Dict[str, Any],
    object_types: Dict[str, str],
    warnings: List[str],
    param_remap: Optional[Dict[int, Dict[str, Any]]] = None,
) -> Any:
    fluent_name = term.get("fluent")
    if fluent_name not in fluent_map:
        warnings.append(f"Fluent '{fluent_name}' referenced but not defined; skipped.")
        return None

    fluent = fluent_map[fluent_name]
    expected_types = fluent_param_types.get(fluent_name, [])
    args: List[Any] = []
    for idx, binding in enumerate(term.get("params", [])):
        expected_type = expected_types[idx] if idx < len(expected_types) else ROOT_TYPE_NAME
        kind = binding.get("kind")
        if kind == "action_param":
            if action is None:
                warnings.append("Action parameter reference in non-action term; skipped.")
                return None
            param_index = int(binding.get("index", -1))
            if param_index < 0 or param_index >= len(action_param_types):
                warnings.append(f"Action parameter index '{param_index}' out of bounds for atom '{fluent_name}'.")
                return None

            # If a param_remap is provided, use it to either resolve a ground constant
            # or find the correct free-variable UP parameter name.
            if param_remap is not None and param_index in param_remap:
                remap = param_remap[param_index]
                if remap["kind"] == "constant":
                    obj_name = remap["object_name"]
                    safe_obj = safe_id(obj_name or "")
                    resolved = object_map.get(obj_name) or object_map.get(safe_obj)
                    if resolved is None:
                        warnings.append(
                            f"Constant object '{obj_name}' not found in object_map for atom '{fluent_name}'."
                        )
                        return None
                    args.append(resolved)
                    continue
                param_name = remap["up_param"]
            else:
                param_name = f"p{param_index}"

            actual_type = action_param_types[param_index]
            if not types_compatible(actual_type, expected_type):
                warnings.append(
                    f"Type mismatch in atom '{fluent_name}': action parameter '{param_name}' is '{actual_type}' but expected '{expected_type}'."
                )
                return None

            try:
                args.append(action.parameter(param_name))
            except Exception:
                warnings.append(f"Missing action parameter '{param_name}' while building atom.")
                return None
        elif kind == "object":
            obj_name = binding.get("name")
            resolved_name = obj_name
            if obj_name not in object_map:
                safe_name = safe_id(obj_name or "")
                if safe_name and safe_name in object_map:
                    resolved_name = safe_name
                    args.append(object_map[safe_name])
                else:
                    warnings.append(f"Object '{obj_name}' not found for atom '{fluent_name}'.")
                    return None
            else:
                args.append(object_map[obj_name])

            actual_type = object_types.get(str(resolved_name), ROOT_TYPE_NAME)
            if not types_compatible(actual_type, expected_type):
                warnings.append(
                    f"Type mismatch in atom '{fluent_name}': object '{resolved_name}' is '{actual_type}' but expected '{expected_type}'."
                )
                return None
        else:
            warnings.append(f"Unsupported parameter binding '{kind}' in atom '{fluent_name}'.")
            return None

    return fluent(*args)


def collect_effect_specs_from_term(
    term: Dict[str, Any],
    action: Any,
    action_param_types: List[str],
    fluent_map: Dict[str, Any],
    fluent_param_types: Dict[str, List[str]],
    object_map: Dict[str, Any],
    object_types: Dict[str, str],
    warnings: List[str],
    param_remap: Optional[Dict[int, Dict[str, Any]]] = None,
) -> List[Tuple[Any, bool]]:
    kind = term.get("kind")

    if kind == "unsupported":
        warnings.append(f"Unsupported effect operator '{term.get('op')}' ignored.")
        return []

    if kind == "atom":
        atom = term_to_atom(
            term,
            fluent_map,
            fluent_param_types,
            action,
            action_param_types,
            object_map,
            object_types,
            warnings,
            param_remap=param_remap,
        )
        if atom is None:
            return []
        return [(atom, True)]

    if kind == "op":
        op = term.get("op")
        children = term.get("children", [])

        if op == "not" and children:
            atom = term_to_atom(
                children[0],
                fluent_map,
                fluent_param_types,
                action,
                action_param_types,
                object_map,
                object_types,
                warnings,
                param_remap=param_remap,
            )
            if atom is None:
                return []
            return [(atom, False)]

        if op == "and":
            specs: List[Tuple[Any, bool]] = []
            for child in children:
                specs.extend(
                    collect_effect_specs_from_term(
                        child,
                        action,
                        action_param_types,
                        fluent_map,
                        fluent_param_types,
                        object_map,
                        object_types,
                        warnings,
                        param_remap=param_remap,
                    )
                )
            return specs

        warnings.append(f"Unsupported effect composition '{op}' ignored.")
        return []

    warnings.append("Unsupported effect term kind ignored.")
    return []


def add_effects_from_term(
    term: Dict[str, Any],
    action: Any,
    action_param_types: List[str],
    fluent_map: Dict[str, Any],
    fluent_param_types: Dict[str, List[str]],
    object_map: Dict[str, Any],
    object_types: Dict[str, str],
    warnings: List[str],
    param_remap: Optional[Dict[int, Dict[str, Any]]] = None,
) -> None:
    kind = term.get("kind")

    if kind == "unsupported":
        warnings.append(f"Unsupported effect operator '{term.get('op')}' ignored.")
        return

    if kind == "atom":
        atom = term_to_atom(
            term,
            fluent_map,
            fluent_param_types,
            action,
            action_param_types,
            object_map,
            object_types,
            warnings,
            param_remap=param_remap,
        )
        if atom is not None:
            action.add_effect(atom, True)
        return

    if kind == "op":
        op = term.get("op")
        children = term.get("children", [])
        if op == "not" and children:
            atom = term_to_atom(
                children[0],
                fluent_map,
                fluent_param_types,
                action,
                action_param_types,
                object_map,
                object_types,
                warnings,
                param_remap=param_remap,
            )
            if atom is not None:
                action.add_effect(atom, False)
            return
        if op == "and":
            for child in children:
                add_effects_from_term(
                    child,
                    action,
                    action_param_types,
                    fluent_map,
                    fluent_param_types,
                    object_map,
                    object_types,
                    warnings,
                    param_remap=param_remap,
                )
            return

        if op == "oneof":
            if not hasattr(action, "add_oneof_effect"):
                warnings.append("oneof effects are only supported for instantaneous actions; ignored.")
                return

            outcomes: List[List[Tuple[Any, bool]]] = []
            for child in children:
                specs = collect_effect_specs_from_term(
                    child,
                    action,
                    action_param_types,
                    fluent_map,
                    fluent_param_types,
                    object_map,
                    object_types,
                    warnings,
                    param_remap=param_remap,
                )
                if specs:
                    outcomes.append(specs)

            if len(outcomes) >= 2:
                action.add_oneof_effect(outcomes)
                return

            if len(outcomes) == 1:
                for atom, value in outcomes[0]:
                    action.add_effect(atom, value)
                warnings.append("oneof effect collapsed to a single valid outcome; applied deterministically.")
                return

            warnings.append("oneof effect had no valid outcomes; ignored.")
            return

        warnings.append(f"Unsupported effect composition '{op}' ignored.")


def apply_init_term(
    problem: Any,
    term: Dict[str, Any],
    fluent_map: Dict[str, Any],
    fluent_param_types: Dict[str, List[str]],
    object_map: Dict[str, Any],
    object_types: Dict[str, str],
    warnings: List[str],
) -> None:
    kind = term.get("kind")
    if kind == "atom":
        atom = term_to_atom(term, fluent_map, fluent_param_types, None, [], object_map, object_types, warnings)
        if atom is not None:
            problem.set_initial_value(atom, True)
        return

    if kind == "op" and term.get("op") == "not" and term.get("children"):
        atom = term_to_atom(
            term["children"][0],
            fluent_map,
            fluent_param_types,
            None,
            [],
            object_map,
            object_types,
            warnings,
        )
        if atom is not None:
            problem.set_initial_value(atom, False)
        return

    if kind == "op" and term.get("op") == "and":
        for child in term.get("children", []):
            apply_init_term(problem, child, fluent_map, fluent_param_types, object_map, object_types, warnings)
        return

    warnings.append("Unsupported Init term ignored.")


def apply_trajectory_constraint(
    problem: Any,
    term: Dict[str, Any],
    fluent_map: Dict[str, Any],
    fluent_param_types: Dict[str, List[str]],
    object_map: Dict[str, Any],
    object_types: Dict[str, str],
    And: Any,
    Or: Any,
    Not: Any,
    Always: Any,
    Sometime: Any,
    AtMostOnce: Any,
    SometimeBefore: Any,
    SometimeAfter: Any,
    warnings: List[str],
) -> None:
    constraint = term_to_trajectory_constraint(
        term,
        fluent_map,
        fluent_param_types,
        object_map,
        object_types,
        And,
        Or,
        Not,
        Always,
        Sometime,
        AtMostOnce,
        SometimeBefore,
        SometimeAfter,
        warnings,
    )
    if constraint is not None:
        problem.add_trajectory_constraint(constraint)


def term_to_trajectory_constraint(
    term: Dict[str, Any],
    fluent_map: Dict[str, Any],
    fluent_param_types: Dict[str, List[str]],
    object_map: Dict[str, Any],
    object_types: Dict[str, str],
    And: Any,
    Or: Any,
    Not: Any,
    Always: Any,
    Sometime: Any,
    AtMostOnce: Any,
    SometimeBefore: Any,
    SometimeAfter: Any,
    warnings: List[str],
) -> Any:
    kind = term.get("kind")
    if kind == "unsupported":
        warnings.append(f"Unsupported trajectory constraint operator '{term.get('op')}' ignored.")
        return None

    if kind != "op":
        warnings.append("Trajectory constraint term is not an operator; ignored.")
        return None

    op = str(term.get("op") or "").lower()
    children = term.get("children", [])

    if op in {"preferences", "preference"}:
        warnings.append("Preference constraint encountered; soft preferences are currently skipped.")
        return None

    if op == "and":
        parsed_children = [
            term_to_trajectory_constraint(
                child,
                fluent_map,
                fluent_param_types,
                object_map,
                object_types,
                And,
                Or,
                Not,
                Always,
                Sometime,
                AtMostOnce,
                SometimeBefore,
                SometimeAfter,
                warnings,
            )
            for child in children
        ]
        parsed_children = [child for child in parsed_children if child is not None]
        if not parsed_children:
            return None
        return And(*parsed_children)

    if op in {"always", "sometime", "at-most-once"}:
        if not children:
            warnings.append(f"Trajectory operator '{op}' had no child expression.")
            return None
        expr = term_to_goal(
            children[0],
            fluent_map,
            fluent_param_types,
            object_map,
            object_types,
            And,
            Or,
            Not,
            warnings,
        )
        if expr is None:
            return None
        if op == "always":
            return Always(expr)
        if op == "sometime":
            return Sometime(expr)
        return AtMostOnce(expr)

    if op in {"sometime-before", "sometime-after"}:
        if len(children) < 2:
            warnings.append(f"Trajectory operator '{op}' requires two child expressions.")
            return None
        left = term_to_goal(
            children[0],
            fluent_map,
            fluent_param_types,
            object_map,
            object_types,
            And,
            Or,
            Not,
            warnings,
        )
        right = term_to_goal(
            children[1],
            fluent_map,
            fluent_param_types,
            object_map,
            object_types,
            And,
            Or,
            Not,
            warnings,
        )
        if left is None or right is None:
            return None
        if op == "sometime-before":
            return SometimeBefore(left, right)
        return SometimeAfter(left, right)

    warnings.append(f"Unsupported trajectory operator '{op}' ignored.")
    return None


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
