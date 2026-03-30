from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import importlib
import io
import os
import sys
from dataclasses import dataclass, field
from itertools import product
from pathlib import Path
from typing import Any, Optional, Sequence


_Planner_ROOT = Path(__file__).resolve().parent
_PR2_ROOT = _Planner_ROOT / "pr2"
_TRANSLATE_ROOT = _PR2_ROOT / "src" / "translate"


@dataclass(frozen=True)
class LoweredUPProblem:
    """PR2-side artifacts lowered from a unified-planning problem."""

    task: Any
    domain_name: str
    problem_name: str
    requirements: tuple[str, ...] = field(default_factory=tuple)
    domain_pddl: str = ""
    problem_pddl: str = ""
    source_problem: Any = None


class LoweringError(NotImplementedError):
    """Raised when a UP problem uses features not supported by the PR2 bridge."""


@dataclass(frozen=True)
class _TranslateModules:
    translate: Any
    normalize: Any
    options: Any
    pddl: Any


_TRANSLATE_MODULES: Optional[_TranslateModules] = None


def lower_problem(problem: Any) -> LoweredUPProblem:
    """Lower a unified-planning problem into PR2's internal task model.

    Supported subset:
    - action-based classical problems
    - typed objects and parameters
    - boolean fluents
    - conjunction, disjunction, negation, equality in conditions/goals
    - unconditional and conditional boolean assignment effects
    - native oneof action outcomes on the vendored unified-planning fork
    """
    up = _import_unified_planning()
    if not _looks_like_up_problem(problem):
        raise TypeError("lower_problem expects a unified-planning Problem.")
    if type(problem).__name__ != "Problem":
        raise LoweringError(
            f"Only classical unified-planning Problem instances are supported, got {type(problem).__name__}."
        )
    if getattr(problem, "quality_metrics", None):
        raise LoweringError("PR2 bridge does not support unified-planning quality metrics yet.")
    if getattr(problem, "timed_effects", None):
        timed_effects = problem.timed_effects
        if timed_effects:
            raise LoweringError("PR2 bridge does not support timed effects.")
    if getattr(problem, "trajectory_constraints", None):
        if problem.trajectory_constraints:
            raise LoweringError("PR2 bridge does not support trajectory constraints.")

    modules = _load_translate_modules()
    pddl = modules.pddl
    operator_kind = up.model.OperatorKind

    requirements: set[str] = {":strips"}
    domain_name = f"{problem.name}_domain"
    problem_name = problem.name

    types = [pddl.Type("object")]
    for user_type in problem.user_types:
        base_name = user_type.father.name if user_type.father is not None else "object"
        types.append(pddl.Type(user_type.name, base_name))

    for pddl_type in types:
        pddl_type.supertype_names = []
    type_by_name = {pddl_type.name: pddl_type for pddl_type in types}
    for pddl_type in types:
        current = pddl_type.basetype_name
        while current:
            pddl_type.supertype_names.append(current)
            parent = type_by_name.get(current)
            current = parent.basetype_name if parent is not None else None

    if problem.user_types:
        requirements.add(":typing")

    objects = [
        pddl.TypedObject(obj.name, _type_name(obj.type))
        for obj in problem.all_objects
    ]

    predicates = []
    for fluent in problem.fluents:
        if not fluent.type.is_bool_type():
            raise LoweringError(
                f"Only boolean fluents are supported on the PR2 bridge, got fluent '{fluent.name}' of type {fluent.type}."
            )
        parameters = [
            pddl.TypedObject(_parameter_name(parameter.name), _type_name(parameter.type))
            for parameter in fluent.signature
        ]
        predicates.append(pddl.Predicate(fluent.name, parameters))
    predicates.append(
        pddl.Predicate(
            "=",
            [pddl.TypedObject("?x", "object"), pddl.TypedObject("?y", "object")],
        )
    )

    init = []
    for fluent_exp, value_exp in problem.initial_values.items():
        if not value_exp.is_bool_constant():
            raise LoweringError("Only boolean initial values are supported on the PR2 bridge.")
        if value_exp.bool_constant_value():
            init.append(_convert_literal_expr(fluent_exp, pddl, negated=False))
    init.extend(pddl.Atom("=", (obj.name, obj.name)) for obj in objects)

    goal_expr = _combine_conditions(problem.goals)
    goal = _convert_condition(goal_expr, pddl, operator_kind, requirements)

    actions = []
    for action in problem.actions:
        if type(action).__name__ != "InstantaneousAction":
            raise LoweringError(
                f"Only instantaneous actions are supported on the PR2 bridge, got {type(action).__name__}."
            )
        if getattr(action, "simulated_effect", None) is not None:
            raise LoweringError(f"Simulated effects are not supported for action '{action.name}'.")

        parameters = [
            pddl.TypedObject(_parameter_name(parameter.name), _type_name(parameter.type))
            for parameter in action.parameters
        ]
        precondition_expr = _combine_conditions(action.preconditions)
        precondition = _convert_condition(precondition_expr, pddl, operator_kind, requirements)

        base_effects = [
            _convert_assignment_effect(effect, pddl, operator_kind, requirements, up, action.name)
            for effect in action.effects
        ]

        oneof_groups = tuple(getattr(action, "oneof_effects", []))
        if not oneof_groups:
            actions.append(
                pddl.Action(
                    action.name,
                    parameters,
                    len(parameters),
                    precondition,
                    base_effects,
                    None,
                )
            )
            continue

        requirements.add(":non-deterministic")
        converted_groups = []
        label_groups = []
        for group in oneof_groups:
            converted_groups.append(
                [
                    tuple(
                        _convert_oneof_effect(effect, pddl, operator_kind, requirements)
                        for effect in outcome
                    )
                    for outcome in group.outcomes
                ]
            )
            label_groups.append(tuple(group.labels))

        for combo_index, (outcome_tuple, label_tuple) in enumerate(
            zip(product(*converted_groups), product(*label_groups)),
            start=1,
        ):
            combo_effects = list(base_effects)
            for outcome_effects in outcome_tuple:
                combo_effects.extend(outcome_effects)
            suffix = "__".join(label_tuple) if label_tuple else str(combo_index)
            actions.append(
                pddl.Action(
                    f"{action.name}_DETDUP_{suffix}",
                    parameters,
                    len(parameters),
                    precondition,
                    combo_effects,
                    None,
                )
            )

    task = pddl.Task(
        domain_name,
        problem_name,
        pddl.Requirements(sorted(requirements)),
        types,
        objects,
        predicates,
        [],
        init,
        goal,
        actions,
        [],
        False,
    )

    domain_pddl, problem_pddl = _serialize_problem_with_up(problem)
    return LoweredUPProblem(
        task=task,
        domain_name=domain_name,
        problem_name=problem_name,
        requirements=tuple(sorted(requirements)),
        domain_pddl=domain_pddl,
        problem_pddl=problem_pddl,
        source_problem=problem,
    )


def task_to_sas(lowered_problem: LoweredUPProblem, output_path: str | Path) -> None:
    """Translate a lowered PR2 task into a SAS task file."""
    modules = _load_translate_modules()
    _configure_translate_options(modules.options)
    modules.translate.simplified_effect_condition_counter = 0
    modules.translate.added_implied_precondition_counter = 0

    # Keep CLI/example output stable by default; set PR2_TRANSLATE_VERBOSE=1
    # to inspect translator diagnostics during debugging.
    verbose_translate = os.getenv("PR2_TRANSLATE_VERBOSE", "").lower() in {"1", "true", "yes", "on"}
    if verbose_translate:
        modules.normalize.normalize(lowered_problem.task)
        sas_task = modules.translate.pddl_to_sas(lowered_problem.task)
    else:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            modules.normalize.normalize(lowered_problem.task)
            sas_task = modules.translate.pddl_to_sas(lowered_problem.task)

    with open(output_path, "w") as output_file:
        sas_task.output(output_file)


def _combine_conditions(expressions: Sequence[Any]) -> Any:
    if not expressions:
        return None
    if len(expressions) == 1:
        return expressions[0]
    first = expressions[0]
    return first.environment.expression_manager.And(*expressions)


def _convert_condition(expr: Any, pddl: Any, operator_kind: Any, requirements: set[str], *, negated: bool = False) -> Any:
    if expr is None:
        return pddl.Truth() if not negated else pddl.Falsity()

    node_type = expr.node_type
    if node_type == operator_kind.BOOL_CONSTANT:
        value = expr.bool_constant_value()
        if negated:
            value = not value
        return pddl.Truth() if value else pddl.Falsity()

    if node_type == operator_kind.NOT:
        return _convert_condition(expr.args[0], pddl, operator_kind, requirements, negated=not negated)

    if node_type == operator_kind.AND:
        parts = [
            _convert_condition(arg, pddl, operator_kind, requirements, negated=negated)
            for arg in expr.args
        ]
        return pddl.Disjunction(parts) if negated else pddl.Conjunction(parts)

    if node_type == operator_kind.OR:
        requirements.add(":disjunctive-preconditions")
        parts = [
            _convert_condition(arg, pddl, operator_kind, requirements, negated=negated)
            for arg in expr.args
        ]
        return pddl.Conjunction(parts) if negated else pddl.Disjunction(parts)

    if node_type == operator_kind.EQUALS:
        requirements.add(":equality")
        return _convert_equals(expr, pddl, negated=negated)

    if node_type == operator_kind.FLUENT_EXP:
        if negated:
            requirements.add(":negative-preconditions")
        return _convert_literal_expr(expr, pddl, negated=negated)

    if node_type in (operator_kind.EXISTS, operator_kind.FORALL):
        raise LoweringError("Quantified conditions are not supported on the PR2 bridge yet.")

    raise LoweringError(f"Unsupported condition node type for PR2 lowering: {node_type}.")


def _convert_equals(expr: Any, pddl: Any, *, negated: bool) -> Any:
    args = tuple(_convert_term_name(arg) for arg in expr.args)
    if negated:
        return pddl.NegatedAtom("=", args)
    return pddl.Atom("=", args)


def _convert_literal_expr(expr: Any, pddl: Any, *, negated: bool) -> Any:
    if not expr.is_fluent_exp():
        raise LoweringError(f"Expected fluent expression, got {expr}.")
    fluent = expr.fluent()
    args = tuple(_convert_term_name(arg) for arg in expr.args)
    if negated:
        return pddl.NegatedAtom(fluent.name, args)
    return pddl.Atom(fluent.name, args)


def _convert_term_name(term: Any) -> str:
    if term.is_parameter_exp():
        return _parameter_name(term.parameter().name)
    if term.is_object_exp():
        return term.object().name
    raise LoweringError(f"Unsupported term in PR2 lowering: {term}.")


def _parameter_name(name: str) -> str:
    return name if name.startswith("?") else f"?{name}"


def _type_name(type_obj: Any) -> str:
    if not type_obj.is_user_type():
        raise LoweringError(f"Only user-defined object types are supported, got {type_obj}.")
    return type_obj.name


def _convert_assignment_effect(effect: Any, pddl: Any, operator_kind: Any, requirements: set[str], up: Any, action_name: str) -> Any:
    if effect.kind != up.model.EffectKind.ASSIGN:
        raise LoweringError(
            f"Only assignment effects are supported on the PR2 bridge, got {effect.kind} on action '{action_name}'."
        )
    if not effect.value.is_bool_constant():
        raise LoweringError(
            f"Only boolean constant effects are supported on the PR2 bridge for action '{action_name}'."
        )
    if not effect.condition.is_true():
        requirements.add(":conditional-effects")
    literal = _convert_literal_expr(
        effect.fluent,
        pddl,
        negated=not effect.value.bool_constant_value(),
    )
    condition = _convert_condition(effect.condition, pddl, operator_kind, requirements)
    return pddl.Effect([], condition, literal)


def _convert_oneof_effect(effect: Any, pddl: Any, operator_kind: Any, requirements: set[str]) -> Any:
    if not effect.value.is_bool_constant():
        raise LoweringError("Only boolean constant oneof effects are supported on the PR2 bridge.")
    if not effect.condition.is_true():
        requirements.add(":conditional-effects")
    literal = _convert_literal_expr(
        effect.fluent,
        pddl,
        negated=not effect.value.bool_constant_value(),
    )
    condition = _convert_condition(effect.condition, pddl, operator_kind, requirements)
    return pddl.Effect([], condition, literal)


def _serialize_problem_with_up(problem: Any) -> tuple[str, str]:
    try:
        from unified_planning.io import PDDLWriter
    except ImportError:
        return "", ""

    try:
        writer = PDDLWriter(problem)
        return writer.get_domain(), writer.get_problem()
    except Exception:
        return "", ""


def _load_translate_modules() -> _TranslateModules:
    global _TRANSLATE_MODULES
    if _TRANSLATE_MODULES is not None:
        return _TRANSLATE_MODULES

    translate_path = str(_TRANSLATE_ROOT)
    if translate_path not in sys.path:
        sys.path.insert(0, translate_path)

    old_argv = sys.argv[:]
    try:
        for module_name in [
            name
            for name in list(sys.modules)
            if name == "pddl" or name == "pddl_parser" or name.startswith("pddl_parser.")
        ]:
            sys.modules.pop(module_name, None)
        sys.argv = [
            "translate.py",
            "domain.pddl",
            "problem.pddl",
            "--keep-unimportant-variables",
            "--invariant-generation-max-time",
            "300",
        ]
        translate = importlib.import_module("translate")
        normalize = importlib.import_module("normalize")
        options = importlib.import_module("options")
        pddl = importlib.import_module("pddl")
    finally:
        sys.argv = old_argv

    _TRANSLATE_MODULES = _TranslateModules(
        translate=translate,
        normalize=normalize,
        options=options,
        pddl=pddl,
    )
    return _TRANSLATE_MODULES


def _configure_translate_options(options: Any) -> None:
    options.generate_relaxed_task = False
    options.use_partial_encoding = True
    options.invariant_generation_max_candidates = 100000
    options.invariant_generation_max_time = 300
    options.add_implied_preconditions = False
    options.filter_unreachable_facts = True
    options.reorder_variables = True
    options.filter_unimportant_vars = False
    options.dump_task = False


def _import_unified_planning():
    try:
        import unified_planning as up
    except ImportError as exc:
        raise RuntimeError(
            "unified_planning is required for the UP-to-PR2 bridge. Install it with 'pip install unified-planning'."
        ) from exc
    return up


def _looks_like_up_problem(problem: Any) -> bool:
    return getattr(type(problem), "__module__", "").startswith("unified_planning.") and hasattr(problem, "kind")