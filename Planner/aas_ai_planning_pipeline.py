from __future__ import annotations

import datetime
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


_ACTIVE_TYPE_PARENTS: Dict[str, str] = {}


@dataclass
class AIPlanningSource:
    aas_id: str
    aas_name: str
    ai_planning_submodel: Dict[str, Any]


@dataclass
class PlanningCapability:
    name: str
    semantic_id: str
    resources: Dict[str, str]


@dataclass
class AIPlanningPipelineResult:
    bt_xml: str
    solve_result: Any
    bt_solve_result: Any
    warnings: List[str] = field(default_factory=list)
    capabilities: List[PlanningCapability] = field(default_factory=list)
    artifacts: Dict[str, str] = field(default_factory=dict)


@dataclass
class _ParsedSource:
    aas_id: str
    aas_name: str
    fluents: List[Dict[str, Any]] = field(default_factory=list)
    actions: List[Dict[str, Any]] = field(default_factory=list)
    objects: List[Dict[str, Any]] = field(default_factory=list)
    init_terms: List[Dict[str, Any]] = field(default_factory=list)
    goal_terms: List[Dict[str, Any]] = field(default_factory=list)
    constraints_terms: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def run_ai_planning_pipeline(
    sources: List[AIPlanningSource],
    timeout: Optional[float] = None,
    artifacts_dir: Optional[str] = None,
) -> AIPlanningPipelineResult:
    warnings: List[str] = []
    parsed_sources = [_parse_source(source) for source in sources]
    for parsed in parsed_sources:
        warnings.extend(parsed.warnings)

    merged = _merge_sources(parsed_sources, warnings)
    up_problem = _build_up_problem(merged, warnings, semantic_natural_transitions=True)
    artifacts = _export_problem_artifacts(up_problem, artifacts_dir, warnings)

    solve_result = _solve_up_problem(up_problem, merged, timeout, warnings)
    bt_solve_result = solve_result

    bt_xml, conversion_warnings = _solve_result_to_bt_xml(solve_result)
    warnings.extend(conversion_warnings)

    if bt_xml:
        _write_text_artifact(artifacts, "behavior_tree_xml", "behavior_tree.xml", bt_xml, warnings)

    if solve_result.is_plan:
        plan_text = _extract_plan_text(solve_result)
        if plan_text:
            _write_text_artifact(artifacts, "deterministic_plan", "deterministic_plan.txt", plan_text, warnings)

    capabilities = _build_capabilities(merged)
    return AIPlanningPipelineResult(
        bt_xml=bt_xml,
        solve_result=solve_result,
        bt_solve_result=bt_solve_result,
        warnings=warnings,
        capabilities=capabilities,
        artifacts=artifacts,
    )


def _solve_up_problem(
    problem: Any,
    merged: Dict[str, Any],
    timeout: Optional[float],
    warnings: List[str],
) -> Any:
    from solve import solve as solve_problem

    semantic_result = None
    semantic_error: Optional[Exception] = None

    solve_problem_input = problem
    map_back_action_instance = None
    if list(getattr(problem, "trajectory_constraints", [])):
        compiled_problem, map_back_action_instance = _compile_trajectory_constraints(problem, warnings)
        if compiled_problem is not None:
            warnings.append(
                "Trajectory constraints compiled before solving to match available planner capabilities."
            )
            solve_problem_input = compiled_problem

    try:
        semantic_result = solve_problem(solve_problem_input, backend="auto", timeout=timeout)
    except Exception as exc:
        semantic_error = exc

    if semantic_result is not None and map_back_action_instance is not None and getattr(semantic_result, "is_plan", False):
        try:
            up_result = semantic_result.require_plan_result()
            plan = getattr(up_result, "plan", None)
            if plan is not None:
                up_result.plan = plan.replace_action_instances(map_back_action_instance)
        except Exception as exc:
            warnings.append(f"Could not map compiled plan back to original actions: {exc}")

    if semantic_result is not None and getattr(semantic_result, "is_solved", False):
        return semantic_result

    events_count = sum(1 for a in merged.get("actions", []) if str(a.get("action_kind") or "") == "Event")
    processes_count = sum(1 for a in merged.get("actions", []) if str(a.get("action_kind") or "") == "Process")
    constraints_count = len(merged.get("constraints_terms", []))

    reason = "semantic solve was unsolved"
    if semantic_error is not None:
        reason = f"semantic solve failed ({semantic_error})"

    warnings.append(
        f"Retrying solve with reduced model because {reason}."
    )
    warnings.append(
        "Reduced-model solve disregards unsupported/unsolved semantics: "
        f"Events={events_count}, Processes={processes_count}, Constraints={constraints_count}."
    )

    reduced_problem = _build_up_problem(
        merged,
        warnings,
        semantic_natural_transitions=False,
        drop_natural_transitions=True,
        include_trajectory_constraints=False,
    )
    reduced_result = solve_problem(reduced_problem, backend="auto", timeout=timeout)

    if getattr(reduced_result, "is_solved", False):
        warnings.append("Reduced-model solve succeeded; generated plan/BT excludes dropped semantics.")
        return reduced_result

    if semantic_result is not None:
        return semantic_result
    return reduced_result


def _compile_trajectory_constraints(problem: Any, warnings: List[str]) -> Tuple[Optional[Any], Optional[Any]]:
    try:
        from unified_planning.engines.compilers.trajectory_constraints_remover import (
            TrajectoryConstraintsRemover,
        )

        compiler = TrajectoryConstraintsRemover()
        compilation_result = compiler.compile(problem)
        return compilation_result.problem, compilation_result.map_back_action_instance
    except Exception as exc:
        warnings.append(f"Failed to compile trajectory constraints: {exc}")
        return None, None


def _solve_result_to_bt_xml(solve_result: Any) -> Tuple[str, List[str]]:
    warnings: List[str] = []

    if not getattr(solve_result, "is_solved", False):
        warnings.append("Solve result is unsolved; BT generation skipped.")
        return "", warnings

    if getattr(solve_result, "is_policy", False):
        from pr2_to_bt import bt_to_xml, policy_to_bt

        bt = policy_to_bt(solve_result.require_policy_result())
        return bt_to_xml(bt), warnings

    if getattr(solve_result, "is_plan", False):
        bt_xml = _deterministic_plan_to_bt_xml(solve_result)
        if bt_xml:
            warnings.append("Generated linear BT from deterministic UP plan (PR2 conversion not used).")
            return bt_xml, warnings

        warnings.append("Deterministic plan solve succeeded but plan-to-BT conversion produced no XML.")
        return "", warnings

    warnings.append("Unknown solve result mode; BT generation skipped.")
    return "", warnings


def _deterministic_plan_to_bt_xml(solve_result: Any) -> str:
    from bt_nodes import ActionNode, BehaviorTree, ReactiveSequence, SuccessLeaf
    from bt_xml import bt_to_xml

    up_result = solve_result.require_plan_result()
    plan = getattr(up_result, "plan", None)
    if plan is None:
        return ""

    action_instances = list(getattr(plan, "actions", []))
    children: List[Any] = [_action_instance_to_bt_action(ai) for ai in action_instances]
    children.append(SuccessLeaf())

    tree = BehaviorTree(ReactiveSequence("DeterministicPlan", children))
    return bt_to_xml(tree)


def _action_instance_to_bt_action(action_instance: Any) -> Any:
    from bt_nodes import ActionNode

    action = getattr(action_instance, "action", None)
    if action is None:
        return ActionNode(str(action_instance))

    action_name = str(getattr(action, "name", "") or str(action_instance))
    params: List[str] = []
    for parameter in getattr(action_instance, "actual_parameters", []):
        param_name = str(getattr(parameter, "name", "") or str(parameter))
        params.append(_safe_id(param_name))

    if params:
        return ActionNode(f"{action_name} {' '.join(params)}")
    return ActionNode(action_name)


def _extract_plan_text(solve_result: Any) -> str:
    if not getattr(solve_result, "is_plan", False):
        return ""

    try:
        up_result = solve_result.require_plan_result()
    except Exception:
        return ""

    plan = getattr(up_result, "plan", None)
    if plan is None:
        return ""

    action_instances = list(getattr(plan, "actions", []))
    lines = [_format_action_instance(ai) for ai in action_instances]
    return "\n".join(lines)


def _format_action_instance(action_instance: Any) -> str:
    action = getattr(action_instance, "action", None)
    if action is None:
        return str(action_instance)

    action_name = str(getattr(action, "name", "") or str(action_instance))
    params: List[str] = []
    for parameter in getattr(action_instance, "actual_parameters", []):
        param_name = str(getattr(parameter, "name", "") or str(parameter))
        params.append(_safe_id(param_name))

    if params:
        return f"{action_name} {' '.join(params)}"
    return action_name


def _export_problem_artifacts(problem: Any, artifacts_dir: Optional[str], warnings: List[str]) -> Dict[str, str]:
    out_dir = _resolve_artifacts_dir(artifacts_dir)
    artifacts: Dict[str, str] = {"artifacts_dir": str(out_dir)}

    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        warnings.append(f"Failed to create artifacts directory '{out_dir}': {exc}")
        return artifacts

    try:
        from unified_planning.io import PDDLWriter

        writer = PDDLWriter(problem)
        domain_text = writer.get_domain()
        problem_text = writer.get_problem()

        domain_path = out_dir / "domain.pddl"
        problem_path = out_dir / "problem.pddl"
        domain_path.write_text(domain_text)
        problem_path.write_text(problem_text)

        artifacts["domain_pddl"] = str(domain_path)
        artifacts["problem_pddl"] = str(problem_path)
    except Exception as exc:
        warnings.append(f"Failed to export PDDL artifacts: {exc}")

    return artifacts


def _resolve_artifacts_dir(artifacts_dir: Optional[str]) -> Path:
    if artifacts_dir:
        return Path(artifacts_dir)

    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return Path(__file__).resolve().parent / "output" / "ai_planning_runs" / timestamp


def _write_text_artifact(
    artifacts: Dict[str, str],
    key: str,
    filename: str,
    content: str,
    warnings: List[str],
) -> str:
    out_dir_raw = artifacts.get("artifacts_dir")
    if not out_dir_raw:
        return ""

    out_dir = Path(out_dir_raw)

    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = out_dir / filename
        output_path.write_text(content)
        artifacts[key] = str(output_path)
        return str(output_path)
    except Exception as exc:
        warnings.append(f"Failed to write artifact '{filename}': {exc}")
        return ""


def _parse_source(source: AIPlanningSource) -> _ParsedSource:
    parsed = _ParsedSource(aas_id=source.aas_id, aas_name=source.aas_name or source.aas_id)

    top_elements = source.ai_planning_submodel.get("submodelElements", [])
    domain = _find_collection(top_elements, "Domain")
    problem = _find_collection(top_elements, "Problem")

    if problem:
        _parse_problem(problem, parsed)
    else:
        parsed.warnings.append(f"{parsed.aas_name}: AIPlanning.Problem section missing.")

    source_objects = [obj["name"] for obj in parsed.objects]
    if domain:
        _parse_domain(domain, parsed, source_objects)
    else:
        parsed.warnings.append(f"{parsed.aas_name}: AIPlanning.Domain section missing.")

    return parsed


def _parse_domain(domain: Dict[str, Any], parsed: _ParsedSource, source_objects: List[str]) -> None:
    domain_sections = domain.get("value", [])

    fluent_section = _find_collection(domain_sections, "Fluents")
    if fluent_section:
        for fluent in fluent_section.get("value", []):
            parsed.fluents.append(_parse_fluent(fluent, parsed.aas_name))

    action_section = _find_collection(domain_sections, "Actions")
    if action_section:
        for action in action_section.get("value", []):
            parsed.actions.append(
                _parse_action(action, parsed.aas_name, parsed.warnings, source_objects, action_kind="Action")
            )

    process_section = _find_collection(domain_sections, "Processes")
    if process_section:
        for process in process_section.get("value", []):
            parsed.actions.append(
                _parse_action(process, parsed.aas_name, parsed.warnings, source_objects, action_kind="Process")
            )

    event_section = _find_collection(domain_sections, "Events")
    if event_section:
        for event in event_section.get("value", []):
            parsed.actions.append(
                _parse_action(event, parsed.aas_name, parsed.warnings, source_objects, action_kind="Event")
            )

    constraint_section = _find_collection(domain_sections, "Constraints")
    if constraint_section is not None:
        parsed.constraints_terms.extend(_parse_constraint_terms(constraint_section, parsed.aas_name, source_objects))


def _parse_problem(problem: Dict[str, Any], parsed: _ParsedSource) -> None:
    sections = problem.get("value", [])

    objects_section = _find_list(sections, "Objects")
    object_names: List[str] = []
    if objects_section:
        for obj in objects_section.get("value", []):
            name = _display_name(obj) or f"Object_{len(object_names) + 1}"
            object_names.append(name)
            parsed.objects.append(
                {
                    "name": name,
                    "reference": _reference_key_tail(obj.get("value")),
                    "declared_type": _parameter_type_from_reference(obj.get("value")),
                    "source_aas_id": parsed.aas_id,
                    "source_aas_name": parsed.aas_name,
                }
            )

    init_section = _find_collection(sections, "Init")
    if init_section:
        for term in init_section.get("value", []):
            node = _parse_term(term, parsed.aas_name, object_names)
            if node is not None:
                parsed.init_terms.append(node)

    goal_section = _find_collection(sections, "Goal")
    if goal_section:
        for term in goal_section.get("value", []):
            node = _parse_term(term, parsed.aas_name, object_names)
            if node is not None:
                parsed.goal_terms.append(node)

    constraint_section = _find_collection(sections, "Constraints")
    if constraint_section is not None:
        parsed.constraints_terms.extend(_parse_constraint_terms(constraint_section, parsed.aas_name, object_names))

    if _find_collection(sections, "Metric") is not None:
        parsed.warnings.append(
            f"{parsed.aas_name}: Problem.Metric present; ignored in v1 best-effort pipeline."
        )


def _parse_fluent(fluent: Dict[str, Any], source_name: str) -> Dict[str, Any]:
    param_types: List[str] = []
    params_list = _find_list(fluent.get("value", []), "Parameters")
    if params_list:
        for param in params_list.get("value", []):
            param_types.append(_parameter_type_from_reference(param.get("value")))

    transformation = None
    value_type = "bool"
    for child in fluent.get("value", []):
        if child.get("modelType") == "Property" and child.get("idShort") == "Transformation":
            transformation = child.get("value")
        if child.get("modelType") == "Property" and child.get("idShort") == "Value":
            numeric_value = child.get("value")
            if _coerce_numeric_literal(numeric_value) is not None:
                value_type = "numeric"

    return {
        "key": fluent.get("idShort") or _display_name(fluent) or "Fluent",
        "semantic_id": _first_semantic_id(fluent),
        "param_types": param_types,
        "transformation": transformation,
        "value_type": value_type,
        "source": source_name,
    }


def _parse_action(
    action: Dict[str, Any],
    source_name: str,
    warnings: List[str],
    source_objects: List[str],
    action_kind: str,
) -> Dict[str, Any]:
    values = action.get("value", [])

    action_key = action.get("idShort") or _display_name(action) or "Action"
    skill_target = action_key

    skill_ref = _find_reference(values, "SkillReference")
    if skill_ref is not None:
        skill_target = _reference_key_tail(skill_ref.get("value")) or action_key

    parameters: List[Dict[str, Any]] = []
    params_list = _find_list(values, "Parameters")
    if params_list:
        for idx, param in enumerate(params_list.get("value", [])):
            parameters.append(
                {
                    "name": _display_name(param) or f"p{idx}",
                    "type": _parameter_type_from_reference(param.get("value")),
                }
            )

    preconditions: List[Dict[str, Any]] = []
    effects: List[Dict[str, Any]] = []

    cond_section = _find_collection(values, "Conditions")
    if cond_section:
        for group in cond_section.get("value", []):
            for term in group.get("value", []):
                node = _parse_term(term, source_name, source_objects)
                if node is not None:
                    preconditions.append(node)

    eff_section = _find_collection(values, "Effects")
    if eff_section:
        for group in eff_section.get("value", []):
            for term in group.get("value", []):
                node = _parse_term(term, source_name, source_objects)
                if node is not None:
                    effects.append(node)

    if not preconditions:
        warnings.append(f"{source_name}: {action_kind} '{action_key}' has no parsed preconditions.")
    if not effects:
        warnings.append(f"{source_name}: {action_kind} '{action_key}' has no parsed effects.")

    return {
        "key": action_key,
        "semantic_id": _first_semantic_id(action),
        "skill_target": skill_target,
        "parameters": parameters,
        "preconditions": preconditions,
        "effects": effects,
        "action_kind": action_kind,
        "source_name": source_name,
        "source_aas_id": "",
    }


def _parse_constraint_terms(
    constraints_section: Dict[str, Any],
    source_name: str,
    source_objects: List[str],
) -> List[Dict[str, Any]]:
    parsed_terms: List[Dict[str, Any]] = []
    for term in constraints_section.get("value", []):
        node = _parse_term(term, source_name, source_objects)
        if node is not None:
            parsed_terms.append(node)
    return parsed_terms


def _parse_term(term: Dict[str, Any], source_name: str, source_objects: List[str]) -> Optional[Dict[str, Any]]:
    model_type = term.get("modelType")
    if model_type == "Property":
        return {
            "kind": "constant",
            "value": term.get("value"),
        }

    if model_type != "SubmodelElementCollection":
        return None

    values = term.get("value", [])
    fluent_ref = _find_reference(values, "FluentReference")

    if fluent_ref is not None:
        fluent_key = _fluent_key_from_reference(fluent_ref.get("value"))
        if not fluent_key:
            fluent_key = _display_name(term) or _semantic_tail(_first_semantic_id(term)) or "Fluent"

        params: List[Dict[str, Any]] = []
        params_list = _find_list(values, "Parameters")
        if params_list:
            for param in params_list.get("value", []):
                resolved = _resolve_parameter_binding(param.get("value"), source_objects)
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
            "semantic_id": _first_semantic_id(term),
        }
        if term_value is not None:
            atom["value"] = term_value
        return atom

    operator = _term_operator(term)
    children: List[Dict[str, Any]] = []
    for child in values:
        if child.get("modelType") == "SubmodelElementCollection":
            parsed_child = _parse_term(child, source_name, source_objects)
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


def _merge_sources(parsed_sources: List[_ParsedSource], warnings: List[str]) -> Dict[str, Any]:
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

            namespaced = _namespace_name(source.aas_name, name)
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

            namespaced = _namespace_name(source.aas_name, key)
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
            remapped_action = _remap_action_fluents(action, fluent_name_map)
            remapped_action["source_aas_id"] = source.aas_id
            remapped_action["source_name"] = source.aas_name
            key = remapped_action["key"]

            if key not in action_by_key:
                remapped_action["sources"] = [(source.aas_id, source.aas_name)]
                remapped_action["fingerprint"] = _action_fingerprint(remapped_action)
                action_by_key[key] = remapped_action
                merged["actions"].append(remapped_action)
                continue

            existing = action_by_key[key]
            new_fp = _action_fingerprint(remapped_action)
            if existing["fingerprint"] == new_fp:
                existing["sources"].append((source.aas_id, source.aas_name))
                continue

            namespaced = _namespace_name(source.aas_name, key)
            warnings.append(
                f"Action '{key}' from {source.aas_name} conflicted; namespaced to '{namespaced}'."
            )
            remapped_action["key"] = namespaced
            remapped_action["sources"] = [(source.aas_id, source.aas_name)]
            remapped_action["fingerprint"] = _action_fingerprint(remapped_action)
            action_by_key[namespaced] = remapped_action
            merged["actions"].append(remapped_action)

        merged["init_terms"].extend(_remap_problem_terms(source.init_terms, fluent_name_map, object_name_map))
        merged["goal_terms"].extend(_remap_problem_terms(source.goal_terms, fluent_name_map, object_name_map))
        merged["constraints_terms"].extend(
            _remap_problem_terms(source.constraints_terms, fluent_name_map, object_name_map)
        )

    return merged


def _build_up_problem(
    merged: Dict[str, Any],
    warnings: List[str],
    semantic_natural_transitions: bool = True,
    drop_natural_transitions: bool = False,
    include_trajectory_constraints: bool = True,
) -> Any:
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
    from unified_planning.model import Event, Process

    problem = Problem("merged_ai_planning")
    all_type_names = _collect_type_names(merged)
    type_parents = _infer_type_parent_map(merged, warnings)
    type_map = _build_type_map(all_type_names, type_parents, UserType, warnings)
    global _ACTIVE_TYPE_PARENTS
    _ACTIVE_TYPE_PARENTS = dict(type_parents)
    entity_type = type_map["Entity"]
    warnings.append("Type constraints are enforced from AAS parameter declarations where available.")

    fluent_map: Dict[str, Any] = {}
    fluent_param_types: Dict[str, List[str]] = {}
    for fluent in merged["fluents"]:
        key = _safe_id(fluent["key"])
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

    for missing_name, arity in _collect_missing_fluents(merged, fluent_map).items():
        safe_name = _safe_id(missing_name)
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
        safe_name = _safe_id(obj["name"])
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
        desired_name = _safe_id(action.get("skill_target") or action["key"]) or _safe_id(action["key"])
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
                expr = _term_to_condition(
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
                _add_effects_from_term(
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
                expr = _term_to_condition(
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
                _add_effects_from_term(
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
                expr = _term_to_condition(
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
                _add_effects_from_term(
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
                expr = _term_to_condition(
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
                if not _add_process_effects_from_term(
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
            expr = _term_to_condition(
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
            _add_effects_from_term(
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
        _apply_init_term(problem, term, fluent_map, fluent_param_types, object_map, object_types, warnings)

    for term in merged["goal_terms"]:
        expr = _term_to_goal(
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
            _apply_trajectory_constraint(
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


def _add_process_effects_from_term(
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
            ok = _add_process_effects_from_term(
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

        target_expr = _term_to_atom(
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

        delta_expr = _term_to_numeric_expression(
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


def _term_to_numeric_expression(
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
        numeric_value = _coerce_numeric_literal(value)
        if numeric_value is not None:
            return numeric_value
        raise ValueError(f"Numeric expression constant must be int/float, got '{value}'.")

    if kind == "atom":
        expr = _term_to_atom(
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

            left = _term_to_numeric_expression(
                children[0],
                action,
                action_param_types,
                fluent_map,
                fluent_param_types,
                object_map,
                object_types,
                warnings,
            )
            right = _term_to_numeric_expression(
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


def _coerce_numeric_literal(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            return None
        try:
            return float(candidate)
        except ValueError:
            return None
    return None

def _collect_type_names(merged: Dict[str, Any]) -> List[str]:
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


def _build_type_map(
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

            base_id = _safe_id(type_name) or "Type"
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

        # Break cycles defensively by attaching remaining types to Entity.
        for type_name in list(pending):
            base_id = _safe_id(type_name) or "Type"
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


def _infer_type_parent_map(merged: Dict[str, Any], warnings: List[str]) -> Dict[str, str]:
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


def _build_capabilities(merged: Dict[str, Any]) -> List[PlanningCapability]:
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


def _collect_missing_fluents(merged: Dict[str, Any], fluent_map: Dict[str, Any]) -> Dict[str, int]:
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
            _accumulate_missing_fluents(term, known, missing)

    return missing


def _accumulate_missing_fluents(term: Dict[str, Any], known: set[str], missing: Dict[str, int]) -> None:
    if term.get("kind") == "atom":
        name = str(term.get("fluent") or "")
        if name and name not in known:
            arity = len(term.get("params", []))
            previous = missing.get(name)
            if previous is None or arity > previous:
                missing[name] = arity
        return

    for child in term.get("children", []):
        _accumulate_missing_fluents(child, known, missing)


def _term_to_condition(
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
        atom = _term_to_atom(
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
            _term_to_condition(
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


def _term_to_goal(
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
        return _term_to_atom(
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
            _term_to_goal(
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


def _term_to_atom(
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
            if not _types_compatible(actual_type, expected_type):
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
                safe_name = _safe_id(obj_name or "")
                if safe_name and safe_name in object_map:
                    resolved_name = safe_name
                    args.append(object_map[safe_name])
                else:
                    warnings.append(f"Object '{obj_name}' not found for atom '{fluent_name}'.")
                    return None
            else:
                args.append(object_map[obj_name])

            actual_type = object_types.get(str(resolved_name), "Entity")
            if not _types_compatible(actual_type, expected_type):
                warnings.append(
                    f"Type mismatch in atom '{fluent_name}': object '{resolved_name}' is '{actual_type}' but expected '{expected_type}'."
                )
                return None
        else:
            warnings.append(f"Unsupported parameter binding '{kind}' in atom '{fluent_name}'.")
            return None

    return fluent(*args)


def _add_effects_from_term(
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
        atom = _term_to_atom(
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
            atom = _term_to_atom(
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
                _add_effects_from_term(
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


def _apply_init_term(
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
        atom = _term_to_atom(term, fluent_map, fluent_param_types, None, [], object_map, object_types, warnings)
        if atom is not None:
            problem.set_initial_value(atom, True)
        return

    if kind == "op" and term.get("op") == "not" and term.get("children"):
        atom = _term_to_atom(
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
            _apply_init_term(problem, child, fluent_map, object_map, warnings)
        return

    warnings.append("Unsupported Init term ignored.")


def _apply_trajectory_constraint(
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
    constraint = _term_to_trajectory_constraint(
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


def _term_to_trajectory_constraint(
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
            _term_to_trajectory_constraint(
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
        expr = _term_to_goal(
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
        left = _term_to_goal(
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
        right = _term_to_goal(
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


def _remap_action_fluents(action: Dict[str, Any], fluent_name_map: Dict[str, str]) -> Dict[str, Any]:
    cloned = json.loads(json.dumps(action))
    cloned["preconditions"] = _remap_terms(cloned["preconditions"], fluent_name_map)
    cloned["effects"] = _remap_terms(cloned["effects"], fluent_name_map)
    return cloned


def _remap_problem_terms(
    terms: List[Dict[str, Any]],
    fluent_name_map: Dict[str, str],
    object_name_map: Dict[str, str],
) -> List[Dict[str, Any]]:
    remapped = _remap_terms(terms, fluent_name_map)
    for term in remapped:
        _remap_term_objects(term, object_name_map)
    return remapped


def _remap_terms(terms: List[Dict[str, Any]], fluent_name_map: Dict[str, str]) -> List[Dict[str, Any]]:
    result = []
    for term in terms:
        cloned = json.loads(json.dumps(term))
        _remap_term_fluent(cloned, fluent_name_map)
        result.append(cloned)
    return result


def _remap_term_fluent(term: Dict[str, Any], fluent_name_map: Dict[str, str]) -> None:
    if term.get("kind") == "atom":
        fluent = term.get("fluent")
        if fluent in fluent_name_map:
            term["fluent"] = fluent_name_map[fluent]
        return

    for child in term.get("children", []):
        _remap_term_fluent(child, fluent_name_map)


def _remap_term_objects(term: Dict[str, Any], object_name_map: Dict[str, str]) -> None:
    if term.get("kind") == "atom":
        for param in term.get("params", []):
            if param.get("kind") == "object":
                name = param.get("name")
                if name in object_name_map:
                    param["name"] = object_name_map[name]
        return

    for child in term.get("children", []):
        _remap_term_objects(child, object_name_map)


def _action_fingerprint(action: Dict[str, Any]) -> str:
    comparable = {
        "action_kind": action.get("action_kind"),
        "skill_target": action.get("skill_target"),
        "parameters": action.get("parameters"),
        "preconditions": action.get("preconditions"),
        "effects": action.get("effects"),
    }
    return json.dumps(comparable, sort_keys=True)


def _namespace_name(source: str, key: str) -> str:
    return f"{_safe_id(source)}__{_safe_id(key)}"


def _safe_id(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", value or "")
    cleaned = cleaned.strip("_")
    if not cleaned:
        return "id"
    if cleaned[0].isdigit():
        return f"id_{cleaned}"
    return cleaned


def _term_operator(term: Dict[str, Any]) -> Optional[str]:
    for sid in term.get("supplementalSemanticIds", []):
        sem = _semantic_from_ref(sid)
        tail = _semantic_tail(sem).lower()
        if tail in {"not", "and", "or"}:
            return tail
        if tail:
            return tail
    return None


def _find_collection(items: List[Dict[str, Any]], id_short: str) -> Optional[Dict[str, Any]]:
    for item in items:
        if item.get("modelType") == "SubmodelElementCollection" and item.get("idShort") == id_short:
            return item
    return None


def _find_list(items: List[Dict[str, Any]], id_short: str) -> Optional[Dict[str, Any]]:
    for item in items:
        if item.get("modelType") == "SubmodelElementList" and item.get("idShort") == id_short:
            return item
    return None


def _find_reference(items: List[Dict[str, Any]], id_short: str) -> Optional[Dict[str, Any]]:
    for item in items:
        if item.get("modelType") == "ReferenceElement" and item.get("idShort") == id_short:
            return item
    return None


def _display_name(item: Dict[str, Any]) -> str:
    display_name = item.get("displayName", [])
    if isinstance(display_name, list):
        for lang in display_name:
            if isinstance(lang, dict) and str(lang.get("language", "")).startswith("en"):
                text = lang.get("text")
                if text:
                    return str(text)
        if display_name and isinstance(display_name[0], dict):
            return str(display_name[0].get("text") or "")
    return str(item.get("idShort") or "")


def _first_semantic_id(item: Dict[str, Any]) -> str:
    sem = item.get("semanticId")
    return _semantic_from_ref(sem)


def _semantic_from_ref(ref: Optional[Dict[str, Any]]) -> str:
    if not isinstance(ref, dict):
        return ""
    keys = ref.get("keys", [])
    if not keys:
        return ""
    return str(keys[0].get("value") or "")


def _semantic_tail(semantic_id: str) -> str:
    if not semantic_id:
        return ""
    if "#" in semantic_id:
        return semantic_id.rsplit("#", 1)[-1]
    return semantic_id.rstrip("/").rsplit("/", 1)[-1]


def _parameter_type_from_reference(reference: Optional[Dict[str, Any]]) -> str:
    if not isinstance(reference, dict):
        return "Entity"

    keys = reference.get("keys", [])
    if not keys:
        return "Entity"

    kind = str(reference.get("type") or "")
    tail = str(keys[-1].get("value") or "")
    if kind == "ExternalReference":
        return _semantic_tail(tail) or "Entity"

    if kind == "ModelReference":
        aas_key = next((k for k in keys if str(k.get("type")) == "AssetAdministrationShell"), None)
        if aas_key is not None:
            aas_value = str(aas_key.get("value") or "")
            return _semantic_tail(aas_value) or "Asset"
        return _semantic_tail(tail) or "Asset"

    return "Entity"


def _reference_key_tail(reference: Optional[Dict[str, Any]]) -> str:
    if not isinstance(reference, dict):
        return ""
    keys = reference.get("keys", [])
    if not keys:
        return ""
    return str(keys[-1].get("value") or "")


def _fluent_key_from_reference(reference: Optional[Dict[str, Any]]) -> str:
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

    # External reference fallback
    return _semantic_tail(values[-1])


def _resolve_parameter_binding(reference: Optional[Dict[str, Any]], source_objects: List[str]) -> Optional[Dict[str, Any]]:
    if not isinstance(reference, dict):
        return None

    keys = reference.get("keys", [])
    values = [str(key.get("value") or "") for key in keys]
    if not values:
        return None

    if "Problem" in values and "Objects" in values:
        index = _last_reference_index(values)
        if index is not None and 0 <= index < len(source_objects):
            return {"kind": "object", "name": source_objects[index]}

    if "Constraints" in values and "Parameters" in values:
        index = _last_reference_index(values)
        if index is not None and 0 <= index < len(source_objects):
            return {"kind": "object", "name": source_objects[index]}

    if "Parameters" in values:
        index = _last_reference_index(values)
        if index is not None:
            return {"kind": "action_param", "index": index}

    if "Objects" in values:
        index = _last_reference_index(values)
        if index is not None and 0 <= index < len(source_objects):
            return {"kind": "object", "name": source_objects[index]}

    tail = values[-1]
    if tail and tail not in {"Parameters", "Objects"}:
        return {"kind": "object", "name": _semantic_tail(tail) or tail}

    return None


def _last_reference_index(values: List[str]) -> Optional[int]:
    for value in reversed(values):
        if value.isdigit():
            return int(value)
    return None


def _types_compatible(actual_type: str, expected_type: str) -> bool:
    actual = str(actual_type or "Entity")
    expected = str(expected_type or "Entity")
    if expected == "Entity":
        return True
    if actual == expected:
        return True

    seen: set[str] = set()
    cursor = actual
    while cursor in _ACTIVE_TYPE_PARENTS and cursor not in seen:
        seen.add(cursor)
        cursor = _ACTIVE_TYPE_PARENTS[cursor]
        if cursor == expected:
            return True
    return False
