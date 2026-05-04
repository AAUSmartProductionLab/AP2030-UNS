from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from ..utils import coerce_numeric_literal, safe_id
from .types import ROOT_TYPE_NAME, canonical_type_name, types_compatible

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

    # Pre-validate UP types before creating the FNode.  UP caches expressions
    # on first construction, so a bad expression created inside fluent(*args)
    # would be returned silently from cache on subsequent calls and then crash
    # add_precondition.  By checking here we avoid polluting the cache.
    try:
        for sig_param, arg in zip(fluent.signature, args):
            arg_type = getattr(arg, "type", None)
            if arg_type is not None and not sig_param.type.is_compatible(arg_type):
                arg_type_name = getattr(arg_type, "name", str(arg_type))
                sig_type_name = getattr(sig_param.type, "name", str(sig_param.type))
                warnings.append(
                    f"UP type mismatch in atom '{fluent_name}': "
                    f"argument type '{arg_type_name}' is not compatible with "
                    f"expected '{sig_type_name}'. Atom skipped."
                )
                return None
    except Exception:
        pass  # if introspection fails, fall through and let UP validate

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


