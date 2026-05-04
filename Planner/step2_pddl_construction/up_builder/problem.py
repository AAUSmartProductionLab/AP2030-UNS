from __future__ import annotations

from typing import Any, Dict, List

from ..models import ActionRef, PlanningCapability, PredicateRef
from ..ontology import load_type_parent_map
from ..utils import safe_id
from . import types as type_system
from .actions import (
    add_effects_from_term,
    add_process_effects_from_term,
    apply_init_term,
    apply_trajectory_constraint,
    collect_missing_fluents,
    term_to_condition,
    term_to_goal,
)
from .bop_encoding import _build_effect_branches
from .fluents import _atom_to_grounded_atom, _is_symbolic_fluent
from .types import (
    ROOT_TYPE_NAME,
    build_type_map,
    canonical_type_name,
    collect_type_names,
    infer_type_parent_map,
    normalize_type_parent_map,
)

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
    planner_action_refs: Dict[str, Dict[str, Any]] = {}
    planner_predicate_refs: Dict[str, Dict[str, Any]] = {}
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
    type_system.ACTIVE_TYPE_PARENTS = dict(type_parents)
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

        source_bindings = list(fluent.get("source_bindings") or [])
        primary_binding = source_bindings[0] if source_bindings else {}
        predicate_ref = PredicateRef(
            fluent_name=key,
            fluent_key=str(fluent.get("key") or key),
            source_aas_id=str(primary_binding.get("aas_id") or fluent.get("source_aas_id") or ""),
            source_aas_name=str(primary_binding.get("aas_name") or fluent.get("source_aas_name") or fluent.get("source") or ""),
            fluent_aas_path=str(primary_binding.get("fluent_aas_path") or fluent.get("fluent_aas_path") or ""),
            transformation_aas_path=str(primary_binding.get("transformation_aas_path") or fluent.get("transformation_aas_path") or ""),
            transformation=str(fluent.get("transformation") or ""),
            param_types=[canonical_type_name(t) for t in fluent.get("param_types", [])],
            source_bindings=source_bindings,
            is_symbolic=_is_symbolic_fluent(fluent),
        )
        planner_predicate_refs[key] = dict(predicate_ref.__dict__)

    for missing_name, arity in collect_missing_fluents(merged, fluent_map).items():
        safe_name = safe_id(missing_name)
        param_names = [f"p{i}" for i in range(arity)]
        params = {name: root_type for name in param_names}
        fluent_obj = problem.add_fluent(safe_name, BoolType(), default_initial_value=False, **params)
        fluent_map[missing_name] = fluent_obj
        fluent_param_types[missing_name] = [ROOT_TYPE_NAME] * arity
        planner_predicate_refs[safe_name] = dict(
            PredicateRef(
                fluent_name=safe_name,
                fluent_key=missing_name,
                source_aas_id="",
                source_aas_name="",
                param_types=[ROOT_TYPE_NAME] * arity,
            ).__dict__
        )
        warnings.append(
            f"Fluent '{missing_name}' was referenced but not declared in Domain.Fluents; auto-declared with arity {arity}."
        )

    # PR4: lookup table used to detect symbolic vs sensor-backed fluents
    # when serializing action effects and the planner-side initial state.
    fluent_lookup: Dict[str, Dict[str, Any]] = {
        str(f.get("key") or ""): f for f in merged.get("fluents", []) if f.get("key")
    }

    def _symbolic_effects_for(
        action: Dict[str, Any],
        param_remap: Dict[int, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        ctx = f"action '{action.get('key') or action.get('skill_target') or '?'}'"
        return _build_effect_branches(
            action.get("effects", []) or [],
            fluent_lookup,
            param_remap=param_remap,
            warnings=warnings,
            context=ctx,
        )

    object_map: Dict[str, Any] = {}
    object_types: Dict[str, str] = {}
    planner_object_refs: Dict[str, Dict[str, str]] = {}
    for obj in merged["objects"]:
        safe_name = safe_id(obj["name"])
        if not safe_name:
            continue
        if obj["name"] in object_map:
            continue

        object_ref = {
            "source_aas_id": str(obj.get("source_aas_id") or ""),
            "source_aas_name": str(obj.get("source_aas_name") or ""),
            "reference": str(obj.get("reference") or ""),
            "object_aas_path": str(obj.get("object_aas_path") or obj.get("reference") or ""),
        }
        planner_object_refs[str(obj["name"])] = object_ref
        planner_object_refs[safe_name] = object_ref

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
            planner_action_refs[desired_name] = dict(
                ActionRef(
                    pddl_action_name=desired_name,
                    source_aas_id=str(action.get("source_aas_id") or ""),
                    source_aas_name=str(action.get("source_name") or ""),
                    action_key=str(action.get("key") or ""),
                    skill_target=str(action.get("skill_target") or action.get("key") or ""),
                    action_kind=action_kind,
                    action_aas_path=str(action.get("action_aas_path") or ""),
                    transformation_aas_path=str(action.get("transformation_aas_path") or ""),
                    transformation=str(action.get("transformation") or ""),
                    parameter_bindings=[
                        {
                            "name": str(param.get("name") or f"p{idx}"),
                            "type": canonical_type_name(param.get("type")),
                            "is_constant": bool(param.get("is_constant")),
                            "bound_object": str(param.get("bound_object") or ""),
                            "resolved_kind": str(param_remap.get(idx, {}).get("kind") or ""),
                            "resolved_up_param": str(param_remap.get(idx, {}).get("up_param") or ""),
                            "resolved_object": str(param_remap.get(idx, {}).get("object_name") or ""),
                        }
                        for idx, param in enumerate(action.get("parameters", []))
                    ],
                    source_bindings=list(action.get("source_bindings") or []),
                    effects=_symbolic_effects_for(action, param_remap),
                ).__dict__
            )
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
            planner_action_refs[desired_name] = dict(
                ActionRef(
                    pddl_action_name=desired_name,
                    source_aas_id=str(action.get("source_aas_id") or ""),
                    source_aas_name=str(action.get("source_name") or ""),
                    action_key=str(action.get("key") or ""),
                    skill_target=str(action.get("skill_target") or action.get("key") or ""),
                    action_kind=action_kind,
                    action_aas_path=str(action.get("action_aas_path") or ""),
                    transformation_aas_path=str(action.get("transformation_aas_path") or ""),
                    transformation=str(action.get("transformation") or ""),
                    parameter_bindings=[
                        {
                            "name": str(param.get("name") or f"p{idx}"),
                            "type": canonical_type_name(param.get("type")),
                            "is_constant": bool(param.get("is_constant")),
                            "bound_object": str(param.get("bound_object") or ""),
                            "resolved_kind": str(param_remap.get(idx, {}).get("kind") or ""),
                            "resolved_up_param": str(param_remap.get(idx, {}).get("up_param") or ""),
                            "resolved_object": str(param_remap.get(idx, {}).get("object_name") or ""),
                        }
                        for idx, param in enumerate(action.get("parameters", []))
                    ],
                    source_bindings=list(action.get("source_bindings") or []),
                    effects=_symbolic_effects_for(action, param_remap),
                ).__dict__
            )
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
            planner_action_refs[desired_name] = dict(
                ActionRef(
                    pddl_action_name=desired_name,
                    source_aas_id=str(action.get("source_aas_id") or ""),
                    source_aas_name=str(action.get("source_name") or ""),
                    action_key=str(action.get("key") or ""),
                    skill_target=str(action.get("skill_target") or action.get("key") or ""),
                    action_kind=action_kind,
                    action_aas_path=str(action.get("action_aas_path") or ""),
                    transformation_aas_path=str(action.get("transformation_aas_path") or ""),
                    transformation=str(action.get("transformation") or ""),
                    parameter_bindings=[
                        {
                            "name": str(param.get("name") or f"p{idx}"),
                            "type": canonical_type_name(param.get("type")),
                            "is_constant": bool(param.get("is_constant")),
                            "bound_object": str(param.get("bound_object") or ""),
                            "resolved_kind": str(param_remap.get(idx, {}).get("kind") or ""),
                            "resolved_up_param": str(param_remap.get(idx, {}).get("up_param") or ""),
                            "resolved_object": str(param_remap.get(idx, {}).get("object_name") or ""),
                        }
                        for idx, param in enumerate(action.get("parameters", []))
                    ],
                    source_bindings=list(action.get("source_bindings") or []),
                    effects=_symbolic_effects_for(action, param_remap),
                ).__dict__
            )
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
                planner_action_refs[desired_name] = dict(
                    ActionRef(
                        pddl_action_name=desired_name,
                        source_aas_id=str(action.get("source_aas_id") or ""),
                        source_aas_name=str(action.get("source_name") or ""),
                        action_key=str(action.get("key") or ""),
                        skill_target=str(action.get("skill_target") or action.get("key") or ""),
                        action_kind=action_kind,
                        action_aas_path=str(action.get("action_aas_path") or ""),
                        transformation_aas_path=str(action.get("transformation_aas_path") or ""),
                        transformation=str(action.get("transformation") or ""),
                        parameter_bindings=[
                            {
                                "name": str(param.get("name") or f"p{idx}"),
                                "type": canonical_type_name(param.get("type")),
                                "is_constant": bool(param.get("is_constant")),
                                "bound_object": str(param.get("bound_object") or ""),
                                "resolved_kind": str(param_remap.get(idx, {}).get("kind") or ""),
                                "resolved_up_param": str(param_remap.get(idx, {}).get("up_param") or ""),
                                "resolved_object": str(param_remap.get(idx, {}).get("object_name") or ""),
                            }
                            for idx, param in enumerate(action.get("parameters", []))
                        ],
                        source_bindings=list(action.get("source_bindings") or []),
                        effects=_symbolic_effects_for(action, param_remap),
                    ).__dict__
                )
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
        planner_action_refs[desired_name] = dict(
            ActionRef(
                pddl_action_name=desired_name,
                source_aas_id=str(action.get("source_aas_id") or ""),
                source_aas_name=str(action.get("source_name") or ""),
                action_key=str(action.get("key") or ""),
                skill_target=str(action.get("skill_target") or action.get("key") or ""),
                action_kind=action_kind,
                action_aas_path=str(action.get("action_aas_path") or ""),
                transformation_aas_path=str(action.get("transformation_aas_path") or ""),
                transformation=str(action.get("transformation") or ""),
                parameter_bindings=[
                    {
                        "name": str(param.get("name") or f"p{idx}"),
                        "type": canonical_type_name(param.get("type")),
                        "is_constant": bool(param.get("is_constant")),
                        "bound_object": str(param.get("bound_object") or ""),
                        "resolved_kind": str(param_remap.get(idx, {}).get("kind") or ""),
                        "resolved_up_param": str(param_remap.get(idx, {}).get("up_param") or ""),
                        "resolved_object": str(param_remap.get(idx, {}).get("object_name") or ""),
                    }
                    for idx, param in enumerate(action.get("parameters", []))
                ],
                source_bindings=list(action.get("source_bindings") or []),
                effects=_symbolic_effects_for(action, param_remap),
            ).__dict__
        )

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

    # Planner metadata drives PR1 XML emission (AAS paths + parameter bindings).
    # Keep both original and case-insensitive lookup keys for robust downstream matching.
    predicate_refs_ci = {
        key.lower(): value for key, value in planner_predicate_refs.items()
    }
    action_refs_ci = {
        key.lower(): value for key, value in planner_action_refs.items()
    }
    object_refs_ci = {
        key.lower(): value for key, value in planner_object_refs.items()
    }

    # PR4: collect the symbolic-only subset of the initial state so the
    # BT runtime can seed SymbolicState. ``init_terms`` are already fully
    # grounded (params come as {kind:"object", name:X}).
    symbolic_initial_state: List[Dict[str, Any]] = []

    def _walk_init_term(term: Dict[str, Any], polarity: bool) -> None:
        if not isinstance(term, dict):
            return
        kind = term.get("kind")
        if kind == "atom":
            atom = _atom_to_grounded_atom(
                term,
                fluent_lookup,
                value=polarity,
                param_remap=None,
                warnings=warnings,
                context="initial state",
            )
            if atom is not None:
                symbolic_initial_state.append(atom)
            return
        if kind == "op":
            op = term.get("op")
            if op == "not":
                for child in term.get("children", []) or []:
                    _walk_init_term(child, not polarity)
                return
            if op == "and":
                for child in term.get("children", []) or []:
                    _walk_init_term(child, polarity)
                return

    for term in merged.get("init_terms", []) or []:
        _walk_init_term(term, True)

    try:
        setattr(
            problem,
            "_planner_metadata",
            {
                "action_refs": planner_action_refs,
                "action_refs_ci": action_refs_ci,
                "predicate_refs": planner_predicate_refs,
                "predicate_refs_ci": predicate_refs_ci,
                "object_refs": planner_object_refs,
                "object_refs_ci": object_refs_ci,
                "initial_state": symbolic_initial_state,
            },
        )
    except Exception:
        warnings.append("Could not attach planner metadata to UP problem; execution refs may be incomplete.")

    return problem



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


