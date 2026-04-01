from __future__ import annotations

from typing import Any, Dict, List, Optional

from .models import PlanningCapability
from .utils import coerce_numeric_literal, safe_id


ACTIVE_TYPE_PARENTS: Dict[str, str] = {}


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
    type_parents = infer_type_parent_map(merged, warnings)
    type_map = build_type_map(all_type_names, type_parents, UserType, warnings)
    global ACTIVE_TYPE_PARENTS
    ACTIVE_TYPE_PARENTS = dict(type_parents)
    entity_type = type_map["Entity"]
    warnings.append("Type constraints are enforced from AAS parameter declarations where available.")

    fluent_map: Dict[str, Any] = {}
    fluent_param_types: Dict[str, List[str]] = {}
    for fluent in merged["fluents"]:
        key = safe_id(fluent["key"])
        if not key:
            continue

        param_names = [f"p{i}" for i, _ in enumerate(fluent["param_types"])]
        params = {
            name: type_map.get(fluent["param_types"][idx], entity_type)
            for idx, name in enumerate(param_names)
        }
        if str(fluent.get("value_type") or "bool") == "numeric":
            fluent_obj = problem.add_fluent(key, RealType(), default_initial_value=0.0, **params)
        else:
            fluent_obj = problem.add_fluent(key, BoolType(), default_initial_value=False, **params)
        fluent_map[fluent["key"]] = fluent_obj
        fluent_param_types[fluent["key"]] = [str(t or "Entity") for t in fluent["param_types"]]

    for missing_name, arity in collect_missing_fluents(merged, fluent_map).items():
        safe_name = safe_id(missing_name)
        param_names = [f"p{i}" for i in range(arity)]
        params = {name: entity_type for name in param_names}
        fluent_obj = problem.add_fluent(safe_name, BoolType(), default_initial_value=False, **params)
        fluent_map[missing_name] = fluent_obj
        fluent_param_types[missing_name] = ["Entity"] * arity
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

        declared_type = str(obj.get("declared_type") or "Entity")
        up_type = type_map.get(declared_type, entity_type)
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

        action_param_types = [str(param.get("type") or "Entity") for param in action["parameters"]]
        params = {
            f"p{i}": type_map.get(action_param_types[i], entity_type)
            for i, _ in enumerate(action["parameters"])
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
    type_names = {"Entity"}

    for fluent in merged.get("fluents", []):
        for ptype in fluent.get("param_types", []):
            type_names.add(str(ptype or "Entity"))

    for action in merged.get("actions", []):
        for parameter in action.get("parameters", []):
            type_names.add(str(parameter.get("type") or "Entity"))

    for obj in merged.get("objects", []):
        type_names.add(str(obj.get("declared_type") or "Entity"))

    return sorted(type_names)


def build_type_map(
    type_names: List[str],
    type_parents: Dict[str, str],
    user_type_ctor: Any,
    warnings: List[str],
) -> Dict[str, Any]:
    entity_type = user_type_ctor("Entity")
    type_map: Dict[str, Any] = {"Entity": entity_type}
    used_ids = {"Entity"}

    pending = [str(type_name or "Entity") for type_name in type_names if str(type_name or "Entity") != "Entity"]
    pending = [type_name for type_name in pending if type_name not in type_map]

    while pending:
        progressed = False
        for type_name in list(pending):
            parent_name = str(type_parents.get(type_name, "Entity") or "Entity")
            if parent_name != "Entity" and parent_name not in type_map and parent_name in pending:
                continue

            parent_type = type_map.get(parent_name, entity_type)
            if parent_name not in type_map and parent_name != "Entity":
                warnings.append(
                    f"Unknown parent type '{parent_name}' for '{type_name}'; attaching to Entity."
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

            warnings.append(f"Type hierarchy cycle detected for '{type_name}'; attaching to Entity.")
            used_ids.add(type_id)
            type_map[type_name] = user_type_ctor(type_id, father=entity_type)
            pending.remove(type_name)

    return type_map


def infer_type_parent_map(merged: Dict[str, Any], warnings: List[str]) -> Dict[str, str]:
    fluent_types = {
        str(fluent.get("key") or ""): [str(t or "Entity") for t in fluent.get("param_types", [])]
        for fluent in merged.get("fluents", [])
    }
    object_types = {
        str(obj.get("name") or ""): str(obj.get("declared_type") or "Entity")
        for obj in merged.get("objects", [])
    }

    parent_map: Dict[str, str] = {}

    def register_parent(child: str, parent: str, context: str) -> None:
        child_t = str(child or "Entity")
        parent_t = str(parent or "Entity")
        if child_t == "Entity" or parent_t == "Entity" or child_t == parent_t:
            return

        existing_parent = parent_map.get(child_t)
        if existing_parent is None:
            parent_map[child_t] = parent_t
            return

        if existing_parent != parent_t:
            warnings.append(
                f"Type parent conflict for '{child_t}' in {context}: keeping '{existing_parent}', ignoring '{parent_t}'."
            )

    def walk_term(term: Dict[str, Any], action_param_types: Optional[List[str]], context: str) -> None:
        if term.get("kind") == "atom":
            fluent_name = str(term.get("fluent") or "")
            expected_types = fluent_types.get(fluent_name, [])

            for idx, binding in enumerate(term.get("params", [])):
                expected_type = expected_types[idx] if idx < len(expected_types) else "Entity"
                if binding.get("kind") == "action_param" and action_param_types is not None:
                    action_idx = int(binding.get("index", -1))
                    if 0 <= action_idx < len(action_param_types):
                        register_parent(action_param_types[action_idx], expected_type, context)
                elif binding.get("kind") == "object":
                    obj_name = str(binding.get("name") or "")
                    actual_type = object_types.get(obj_name, "Entity")
                    register_parent(actual_type, expected_type, context)
            return

        for child in term.get("children", []):
            walk_term(child, action_param_types, context)

    for action in merged.get("actions", []):
        action_param_types = [str(param.get("type") or "Entity") for param in action.get("parameters", [])]
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

    return parent_map


def build_capabilities(merged: Dict[str, Any]) -> List[PlanningCapability]:
    capabilities: List[PlanningCapability] = []

    for action in merged["actions"]:
        if str(action.get("action_kind") or "Action") != "Action":
            continue

        name = action.get("skill_target") or action["key"]
        semantic_id = action.get("semantic_id") or f"https://smartproductionlab.aau.dk/Capability/{name}"

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
) -> Any:
    fluent_name = term.get("fluent")
    if fluent_name not in fluent_map:
        warnings.append(f"Fluent '{fluent_name}' referenced but not defined; skipped.")
        return None

    fluent = fluent_map[fluent_name]
    expected_types = fluent_param_types.get(fluent_name, [])
    args: List[Any] = []
    for idx, binding in enumerate(term.get("params", [])):
        expected_type = expected_types[idx] if idx < len(expected_types) else "Entity"
        kind = binding.get("kind")
        if kind == "action_param":
            if action is None:
                warnings.append("Action parameter reference in non-action term; skipped.")
                return None
            param_index = int(binding.get("index", -1))
            param_name = f"p{param_index}"
            if param_index < 0 or param_index >= len(action_param_types):
                warnings.append(f"Action parameter index '{param_index}' out of bounds for atom '{fluent_name}'.")
                return None

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

            actual_type = object_types.get(str(resolved_name), "Entity")
            if not types_compatible(actual_type, expected_type):
                warnings.append(
                    f"Type mismatch in atom '{fluent_name}': object '{resolved_name}' is '{actual_type}' but expected '{expected_type}'."
                )
                return None
        else:
            warnings.append(f"Unsupported parameter binding '{kind}' in atom '{fluent_name}'.")
            return None

    return fluent(*args)


def add_effects_from_term(
    term: Dict[str, Any],
    action: Any,
    action_param_types: List[str],
    fluent_map: Dict[str, Any],
    fluent_param_types: Dict[str, List[str]],
    object_map: Dict[str, Any],
    object_types: Dict[str, str],
    warnings: List[str],
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
                )
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
    actual = str(actual_type or "Entity")
    expected = str(expected_type or "Entity")
    if expected == "Entity":
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
