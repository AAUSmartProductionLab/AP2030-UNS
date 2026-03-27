"""AI Planning Submodel builder.

This submodel stores planning-relevant information separate from Skills.
Both Domain and Problem sections are optional and can coexist in the same
submodel instance.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from basyx.aas import model

from ..semantic_ids import SemanticIdCatalog
from .skills_spec_parser import (
    normalize_description_from_pddl,
    normalize_parameters,
)


def _make_semantic_id(semantic_id_str: Optional[str]) -> Optional[model.ExternalReference]:
    if not semantic_id_str:
        return None
    return model.ExternalReference(
        (model.Key(type_=model.KeyTypes.GLOBAL_REFERENCE, value=semantic_id_str),)
    )


def _semantic_id_tail(semantic_id_str: Optional[str]) -> Optional[str]:
    if not isinstance(semantic_id_str, str) or not semantic_id_str:
        return None
    fragment_tail = semantic_id_str.rsplit("#", 1)[-1]
    return fragment_tail.rsplit("/", 1)[-1]


def _semantic_id_display_name(semantic_id_str: Optional[str]) -> Optional[str]:
    tail = _semantic_id_tail(semantic_id_str)
    if not tail:
        return None
    normalized = tail.replace("-", " ").replace("_", " ").strip()
    if not normalized:
        return None
    return " ".join(part.capitalize() for part in normalized.split())


@dataclass(frozen=True)
class _TermOwner:
    """Identifies which transition owns parameter indexes for a term tree."""

    section: str
    key: str


@dataclass
class _PlanningBuildContext:
    """Mutable build state shared across AI planning sections."""

    domain_fluents: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    section_parameter_names: Dict[Tuple[str, str], List[str]] = field(default_factory=dict)
    problem_object_names: List[str] = field(default_factory=list)
    problem_preference_locations: Dict[str, Tuple[str, str]] = field(default_factory=dict)

    def reset(self) -> None:
        self.domain_fluents.clear()
        self.section_parameter_names.clear()
        self.problem_object_names.clear()
        self.problem_preference_locations.clear()


class _PlanningReferenceBuilder:
    """Builds references used by AI planning sections."""

    def __init__(self, base_url: str, context: _PlanningBuildContext):
        self._base_url = base_url
        self._context = context

    def build_ai_planning_model_reference(
        self,
        system_id: str,
        path_segments: List[Tuple[model.KeyTypes, str]],
        reference_type: model.KeyTypes,
    ) -> model.ModelReference:
        keys = [
            model.Key(
                type_=model.KeyTypes.SUBMODEL,
                value=f"{self._base_url}/submodels/instances/{system_id}/AIPlanning",
            )
        ]
        keys.extend(model.Key(type_=key_type, value=str(value)) for key_type, value in path_segments)
        return model.ModelReference(key=tuple(keys), type_=reference_type)

    def build_model_reference_from_dsl(self, system_id: str, model_ref: Any) -> model.ModelReference:
        if not isinstance(model_ref, list) or not model_ref:
            raise ValueError("Invalid modelRef: expected non-empty list")

        keys: List[model.Key] = []
        last_type = model.KeyTypes.REFERENCE_ELEMENT
        for part in model_ref:
            if not isinstance(part, dict) or not part:
                continue

            k, v = next(iter(part.items()))
            if k == "AAS":
                last_type = model.KeyTypes.ASSET_ADMINISTRATION_SHELL
                if v == "self":
                    v = f"{self._base_url}/aas/{system_id}"
            elif k == "SM":
                last_type = model.KeyTypes.SUBMODEL
                v = f"{self._base_url}/submodels/instances/{system_id}/{v}"
            elif k == "SMC":
                last_type = model.KeyTypes.SUBMODEL_ELEMENT_COLLECTION
            elif k == "SML":
                last_type = model.KeyTypes.SUBMODEL_ELEMENT_LIST
            elif k == "ReferenceElement":
                last_type = model.KeyTypes.REFERENCE_ELEMENT
            elif k == "Property":
                last_type = model.KeyTypes.PROPERTY

            keys.append(model.Key(last_type, str(v)))

        if not keys:
            raise ValueError("Invalid modelRef: no valid key segments found")

        return model.ModelReference(key=tuple(keys), type_=last_type)

    def build_preference_declaration_reference(
        self,
        system_id: str,
        preference_name: str,
    ) -> model.ModelReference:
        location = self._context.problem_preference_locations.get(preference_name)
        if location is None:
            raise ValueError(
                f"Metric references unknown preference '{preference_name}'. Declare it in Problem.Goal or Problem.Constraints."
            )

        section_name, term_id_short = location
        return self.build_ai_planning_model_reference(
            system_id=system_id,
            path_segments=[
                (model.KeyTypes.SUBMODEL_ELEMENT_COLLECTION, "Problem"),
                (model.KeyTypes.SUBMODEL_ELEMENT_COLLECTION, section_name),
                (model.KeyTypes.SUBMODEL_ELEMENT_COLLECTION, term_id_short),
            ],
            reference_type=model.KeyTypes.SUBMODEL_ELEMENT_COLLECTION,
        )

    def build_action_parameter_reference(
        self,
        system_id: str,
        owner_section: str,
        owner_key: str,
        param_idx: int,
    ) -> model.ReferenceElement:
        parameter_names = self._context.section_parameter_names.get((str(owner_section), str(owner_key)), [])
        display_name = (
            parameter_names[param_idx]
            if 0 <= param_idx < len(parameter_names)
            else f"Parameter_{param_idx}"
        )

        return model.ReferenceElement(
            id_short=None,
            display_name=model.MultiLanguageNameType({"en": display_name}),
            value=self.build_ai_planning_model_reference(
                system_id=system_id,
                path_segments=[
                    (model.KeyTypes.SUBMODEL_ELEMENT_COLLECTION, "Domain"),
                    (model.KeyTypes.SUBMODEL_ELEMENT_COLLECTION, str(owner_section)),
                    (model.KeyTypes.SUBMODEL_ELEMENT_COLLECTION, str(owner_key)),
                    (model.KeyTypes.SUBMODEL_ELEMENT_LIST, "Parameters"),
                    (model.KeyTypes.REFERENCE_ELEMENT, str(param_idx)),
                ],
                reference_type=model.KeyTypes.REFERENCE_ELEMENT,
            ),
        )

    def build_problem_object_reference(
        self,
        system_id: str,
        section_name: str,
        object_idx: int,
    ) -> model.ReferenceElement:
        if object_idx < 0 or object_idx >= len(self._context.problem_object_names):
            raise ValueError(
                f"Invalid AI-Planning Problem.{section_name} object index {object_idx}: index out of range for Problem.Objects"
            )

        display_name = self._context.problem_object_names[object_idx]
        return model.ReferenceElement(
            id_short=None,
            display_name=model.MultiLanguageNameType({"en": display_name}),
            value=self.build_ai_planning_model_reference(
                system_id=system_id,
                path_segments=[
                    (model.KeyTypes.SUBMODEL_ELEMENT_COLLECTION, "Problem"),
                    (model.KeyTypes.SUBMODEL_ELEMENT_LIST, "Objects"),
                    (model.KeyTypes.REFERENCE_ELEMENT, str(object_idx)),
                ],
                reference_type=model.KeyTypes.REFERENCE_ELEMENT,
            ),
        )

    def append_fluent_reference_element(
        self,
        elements: List[model.SubmodelElement],
        system_id: str,
        ref_name: Any,
        external_ref: Any,
        inferred_semantic_id: Optional[str],
    ) -> Optional[str]:
        if ref_name:
            domain_fluent = self._context.domain_fluents.get(str(ref_name), {})
            resolved_semantic_id = inferred_semantic_id or domain_fluent.get("semantic_id")
            elements.append(
                model.ReferenceElement(
                    id_short="FluentReference",
                    value=self.build_ai_planning_model_reference(
                        system_id=system_id,
                        path_segments=[
                            (model.KeyTypes.SUBMODEL_ELEMENT_COLLECTION, "Domain"),
                            (model.KeyTypes.SUBMODEL_ELEMENT_COLLECTION, "Fluents"),
                            (model.KeyTypes.SUBMODEL_ELEMENT_COLLECTION, str(ref_name)),
                        ],
                        reference_type=model.KeyTypes.SUBMODEL_ELEMENT_COLLECTION,
                    ),
                )
            )
            return resolved_semantic_id

        if external_ref:
            resolved_semantic_id = inferred_semantic_id or str(external_ref)
            elements.append(
                model.ReferenceElement(
                    id_short="FluentReference",
                    value=model.ExternalReference(
                        key=(model.Key(model.KeyTypes.GLOBAL_REFERENCE, str(external_ref)),)
                    ),
                )
            )
            return resolved_semantic_id

        return inferred_semantic_id


class _DomainSectionBuilder:
    """Builds the Domain section using injected section callbacks."""

    def __init__(
        self,
        build_fluents_section: Callable[[List[Dict[str, Any]]], model.SubmodelElementCollection],
        build_actions_section: Callable[[str, List[Dict[str, Any]]], model.SubmodelElementCollection],
        build_processes_section: Callable[[str, Any], model.SubmodelElementCollection],
        build_events_section: Callable[[str, Any], model.SubmodelElementCollection],
        build_constraints_section: Callable[[str, str, Any, bool], model.SubmodelElementCollection],
    ):
        self._build_fluents_section = build_fluents_section
        self._build_actions_section = build_actions_section
        self._build_processes_section = build_processes_section
        self._build_events_section = build_events_section
        self._build_constraints_section = build_constraints_section

    def build(self, system_id: str, domain_cfg: Dict[str, Any]) -> model.SubmodelElementCollection:
        elements: List[model.SubmodelElement] = []

        fluents_cfg = domain_cfg.get("Fluents", []) or []
        if isinstance(fluents_cfg, list) and fluents_cfg:
            elements.append(self._build_fluents_section(fluents_cfg))

        actions_cfg = domain_cfg.get("Actions", []) or []
        if isinstance(actions_cfg, list) and actions_cfg:
            elements.append(self._build_actions_section(system_id, actions_cfg))

        processes_cfg = domain_cfg.get("Processes")
        if processes_cfg:
            elements.append(self._build_processes_section(system_id, processes_cfg))

        events_cfg = domain_cfg.get("Events")
        if events_cfg:
            elements.append(self._build_events_section(system_id, events_cfg))

        constraints_cfg = domain_cfg.get("Constraints")
        if constraints_cfg:
            elements.append(
                self._build_constraints_section(
                    system_id=system_id,
                    section_name="Constraints",
                    constraints_cfg=constraints_cfg,
                    is_problem_section=False,
                )
            )

        return model.SubmodelElementCollection(
            id_short="Domain",
            value=elements,
            semantic_id=_make_semantic_id(SemanticIdCatalog.AI_PLANNING_DOMAIN),
        )


class _ProblemSectionBuilder:
    """Builds the Problem section using injected section callbacks."""

    def __init__(
        self,
        build_problem_objects_section: Callable[[str, Any], model.SubmodelElementList],
        build_problem_state_section: Callable[[str, str, Any], model.SubmodelElementCollection],
        build_constraints_section: Callable[[str, str, Any, bool], model.SubmodelElementCollection],
        build_metric_section: Callable[[str, Any], model.SubmodelElementCollection],
    ):
        self._build_problem_objects_section = build_problem_objects_section
        self._build_problem_state_section = build_problem_state_section
        self._build_constraints_section = build_constraints_section
        self._build_metric_section = build_metric_section

    def build(self, system_id: str, problem_cfg: Dict[str, Any]) -> model.SubmodelElementCollection:
        elements: List[model.SubmodelElement] = []

        objects_cfg = problem_cfg.get("Objects", []) or []
        if objects_cfg:
            elements.append(self._build_problem_objects_section(system_id, objects_cfg))

        initial_state = problem_cfg.get("Init")
        if initial_state:
            elements.append(self._build_problem_state_section(system_id, "Init", initial_state))

        goal_state = problem_cfg.get("Goal")
        if goal_state:
            elements.append(self._build_problem_state_section(system_id, "Goal", goal_state))

        constraints_cfg = problem_cfg.get("Constraints")
        if constraints_cfg:
            elements.append(
                self._build_constraints_section(
                    system_id=system_id,
                    section_name="Constraints",
                    constraints_cfg=constraints_cfg,
                    is_problem_section=True,
                )
            )

        metric_cfg = problem_cfg.get("Metric")
        if metric_cfg:
            elements.append(self._build_metric_section(system_id, metric_cfg))

        preferences_cfg = problem_cfg.get("Preferences")
        if preferences_cfg:
            raise ValueError(
                "Problem.Preferences is deprecated. Declare preferences inside Goal or Constraints and reference them from Metric.preference_weights."
            )

        return model.SubmodelElementCollection(
            id_short="Problem",
            value=elements,
            semantic_id=_make_semantic_id(SemanticIdCatalog.AI_PLANNING_PROBLEM),
        )


class _PlanningTermBuilder:
    """Builds term trees and fluent collections for planning sections."""

    def __init__(
        self,
        references: _PlanningReferenceBuilder,
        typed_property_factory: Callable[[str, Any, Optional[str]], model.Property],
    ):
        self._references = references
        self._typed_property_factory = typed_property_factory

    def build_term(
        self,
        system_id: str,
        action_key: str,
        term_cfg: Dict[str, Any],
        index: int,
        is_effect: bool,
        problem_section_name: Optional[str] = None,
        id_short_override: Optional[str] = None,
        term_owner: Optional[_TermOwner] = None,
    ) -> model.SubmodelElementCollection:
        owner = self.resolve_term_owner(term_owner, fallback_key=action_key)
        term_type = term_cfg.get("type")
        current_term_id_short = id_short_override or f"term_{index}"
        fallback_display = _semantic_id_display_name(term_cfg.get("semantic_id")) or (term_type or current_term_id_short)
        term_display_name = self.resolve_term_display_name(term_cfg, fallback_display)

        if term_type in {"predicate", "function", "fluent"}:
            if problem_section_name:
                return self.build_problem_fluent(
                    system_id,
                    problem_section_name,
                    term_cfg,
                    id_short_override=current_term_id_short,
                    display_name_override=term_display_name,
                )
            return self.build_domain_fluent(
                system_id,
                action_key,
                term_cfg,
                id_short_override=current_term_id_short,
                display_name_override=term_display_name,
                term_owner=owner,
            )

        if term_type == "constant":
            literal = self.build_constant_property(term_cfg, index)
            return model.SubmodelElementCollection(
                id_short=current_term_id_short,
                value=[literal],
                semantic_id=_make_semantic_id(SemanticIdCatalog.PDDL_TERM),
                display_name=model.MultiLanguageNameType({"en": term_display_name}),
            )

        semantic_id_str = term_cfg.get("semantic_id")
        child_terms = term_cfg.get("terms", []) or []
        term_elements: List[model.SubmodelElement] = []

        for i, child in enumerate(child_terms):
            child_type = child.get("type") or child.get("key")
            if child_type == "constant":
                term_elements.append(self.build_constant_property(child, i + 1))
            else:
                term_elements.append(
                    self.build_term(
                        system_id,
                        action_key,
                        child,
                        i + 1,
                        is_effect=is_effect,
                        problem_section_name=problem_section_name,
                        term_owner=owner,
                    )
                )

        return model.SubmodelElementCollection(
            id_short=current_term_id_short,
            value=term_elements,
            semantic_id=_make_semantic_id(SemanticIdCatalog.PDDL_TERM),
            supplemental_semantic_id=[_make_semantic_id(semantic_id_str)] if semantic_id_str else [],
            display_name=model.MultiLanguageNameType({"en": term_display_name}),
        )

    def build_domain_fluent(
        self,
        system_id: str,
        action_key: str,
        fluent_cfg: Dict[str, Any],
        resolve_parameter_refs: bool = True,
        id_short_override: Optional[str] = None,
        display_name_override: Optional[str] = None,
        term_owner: Optional[_TermOwner] = None,
    ) -> model.SubmodelElementCollection:
        elements: List[model.SubmodelElement] = []
        owner = self.resolve_term_owner(term_owner, fallback_key=action_key)

        ref_name = fluent_cfg.get("TransformationReference")
        external_ref = fluent_cfg.get("ExternalReference")
        inferred_semantic_id = fluent_cfg.get("semantic_id")

        inferred_semantic_id = self._references.append_fluent_reference_element(
            elements=elements,
            system_id=system_id,
            ref_name=ref_name,
            external_ref=external_ref,
            inferred_semantic_id=inferred_semantic_id,
        )

        args = fluent_cfg.get("parameters", []) or []
        if resolve_parameter_refs:
            if any(not isinstance(arg, int) for arg in args):
                raise ValueError(
                    f"Invalid AI-Planning Domain.{owner.section}.{owner.key} term arguments: only integer parameter indexes are supported"
                )
            parameter_refs = [
                self._references.build_action_parameter_reference(
                    system_id,
                    owner.section,
                    owner.key,
                    int(arg),
                )
                for arg in args
                if isinstance(arg, int)
            ]
            self.append_parameter_reference_list(elements, parameter_refs)
        else:
            literal_args = [
                self._typed_property_factory(f"Argument_{idx + 1:02d}", arg, None)
                for idx, arg in enumerate(args)
            ]
            if literal_args:
                elements.append(
                    model.SubmodelElementCollection(
                        id_short="Parameters",
                        value=literal_args,
                        semantic_id=_make_semantic_id(SemanticIdCatalog.PDDL_PARAMETERS),
                    )
                )

        if "value" in fluent_cfg and self.should_emit_numeric_value(fluent_cfg):
            elements.append(self._typed_property_factory("Value", fluent_cfg.get("value"), None))

        return self.build_fluent_collection(
            elements=elements,
            fluent_cfg=fluent_cfg,
            inferred_semantic_id=inferred_semantic_id,
            fallback_name=ref_name,
            id_short_override=id_short_override,
            display_name_override=display_name_override,
        )

    def build_problem_fluent(
        self,
        system_id: str,
        section_name: str,
        fluent_cfg: Dict[str, Any],
        id_short_override: Optional[str] = None,
        display_name_override: Optional[str] = None,
    ) -> model.SubmodelElementCollection:
        elements: List[model.SubmodelElement] = []

        ref_name = fluent_cfg.get("TransformationReference")
        external_ref = fluent_cfg.get("ExternalReference")
        preference_ref = fluent_cfg.get("PreferenceReference") or fluent_cfg.get("preference")
        inferred_semantic_id = fluent_cfg.get("semantic_id")

        if section_name == "Metric" and preference_ref:
            pref_name = str(preference_ref)
            inferred_semantic_id = inferred_semantic_id or SemanticIdCatalog.PDDL_METRIC_IS_VIOLATED
            elements.append(
                model.ReferenceElement(
                    id_short="PreferenceReference",
                    value=self._references.build_preference_declaration_reference(system_id, pref_name),
                )
            )
        else:
            inferred_semantic_id = self._references.append_fluent_reference_element(
                elements=elements,
                system_id=system_id,
                ref_name=ref_name,
                external_ref=external_ref,
                inferred_semantic_id=inferred_semantic_id,
            )

        args = fluent_cfg.get("parameters", []) or []
        parameter_refs = [
            self._references.build_problem_object_reference(system_id, section_name, int(arg))
            for arg in args
            if isinstance(arg, int)
        ]
        if len(parameter_refs) != len(args):
            raise ValueError(
                f"Invalid AI-Planning Problem.{section_name} term arguments: only integer object indexes are supported"
            )

        self.append_parameter_reference_list(elements, parameter_refs)

        if "value" in fluent_cfg and self.should_emit_numeric_value(fluent_cfg):
            elements.append(self._typed_property_factory("Value", fluent_cfg.get("value"), None))

        return self.build_fluent_collection(
            elements=elements,
            fluent_cfg=fluent_cfg,
            inferred_semantic_id=inferred_semantic_id,
            fallback_name=ref_name or preference_ref,
            id_short_override=id_short_override,
            display_name_override=display_name_override,
        )

    def resolve_term_owner(self, owner: Optional[_TermOwner], fallback_key: str) -> _TermOwner:
        if owner is not None:
            return owner
        return _TermOwner(section="Actions", key=str(fallback_key))

    def append_parameter_reference_list(
        self,
        elements: List[model.SubmodelElement],
        parameter_refs: List[model.ReferenceElement],
    ) -> None:
        if not parameter_refs:
            return
        elements.append(
            model.SubmodelElementList(
                id_short="Parameters",
                type_value_list_element=model.ReferenceElement,
                value=parameter_refs,
                semantic_id_list_element=_make_semantic_id(SemanticIdCatalog.PDDL_PARAMETER),
            )
        )

    def build_fluent_collection(
        self,
        elements: List[model.SubmodelElement],
        fluent_cfg: Dict[str, Any],
        inferred_semantic_id: Optional[str],
        fallback_name: Optional[Any],
        id_short_override: Optional[str],
        display_name_override: Optional[str],
    ) -> model.SubmodelElementCollection:
        semantic_name = _semantic_id_tail(inferred_semantic_id)
        id_short = id_short_override or str(fallback_name or semantic_name or "Fluent")
        display_name = display_name_override or self.resolve_term_display_name(fluent_cfg, id_short)

        supplemental_ids = []
        pred_sid = _make_semantic_id(inferred_semantic_id)
        if pred_sid:
            supplemental_ids.append(pred_sid)

        return model.SubmodelElementCollection(
            id_short=id_short,
            value=elements,
            display_name=model.MultiLanguageNameType({"en": display_name}),
            semantic_id=pred_sid or _make_semantic_id(SemanticIdCatalog.PDDL_TERM),
            supplemental_semantic_id=[_make_semantic_id(SemanticIdCatalog.PDDL_TERM)] + supplemental_ids
            if pred_sid
            else [],
        )

    def flatten_effect_set(self, term_cfg: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(term_cfg, dict):
            return term_cfg

        semantic_id = str(term_cfg.get("semantic_id", "")).lower()
        if term_cfg.get("type") == "arithmeticterm" and semantic_id.endswith("/set"):
            fluent_term, value_term = self.extract_set_parts(term_cfg.get("terms", []) or [])
            if fluent_term is not None:
                if value_term is not None:
                    fluent_term = dict(fluent_term)
                    fluent_term["value"] = value_term
                return fluent_term

        children = term_cfg.get("terms")
        if isinstance(children, list):
            updated = [self.flatten_effect_set(child) if isinstance(child, dict) else child for child in children]
            flattened = dict(term_cfg)
            flattened["terms"] = updated
            return flattened

        return term_cfg

    def should_emit_numeric_value(self, fluent_cfg: Dict[str, Any]) -> bool:
        value = fluent_cfg.get("value")
        if isinstance(value, bool):
            return False

        term_type = str(fluent_cfg.get("type", "")).lower()
        if term_type == "function":
            return True

        return isinstance(value, (int, float))

    def extract_set_parts(self, terms: List[Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], Optional[Any]]:
        fluent_term: Optional[Dict[str, Any]] = None
        value_term: Optional[Any] = None
        for term in terms:
            if not isinstance(term, dict):
                continue
            if term.get("type") in {"predicate", "function", "fluent"} and fluent_term is None:
                fluent_term = term
            elif term.get("type") == "constant" and value_term is None:
                value_term = term.get("value")
        return fluent_term, value_term

    def build_constant_property(self, term_cfg: Dict[str, Any], index: int) -> model.Property:
        const_name = term_cfg.get("name") or f"Constant_{index}"
        return self._typed_property_factory(
            f"term_{index}",
            term_cfg.get("value"),
            str(const_name),
        )

    def resolve_term_display_name(self, term_cfg: Dict[str, Any], fallback: str) -> str:
        if not isinstance(term_cfg, dict):
            return fallback

        explicit_display = term_cfg.get("display_name") or term_cfg.get("displayName")
        if isinstance(explicit_display, str) and explicit_display.strip():
            return explicit_display.strip()

        for key in ("name", "key", "TransformationReference", "PreferenceReference", "preference"):
            value = term_cfg.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        # External/global predicate references should use the semantic tail
        # (e.g. .../Predicates/On -> On) rather than a generic fallback like
        # "predicate".
        external_reference = term_cfg.get("ExternalReference") or term_cfg.get("externalRef")
        external_tail = _semantic_id_tail(str(external_reference)) if external_reference else None
        if external_tail:
            return external_tail

        semantic_tail = _semantic_id_tail(term_cfg.get("semantic_id"))
        if semantic_tail:
            return semantic_tail

        return fallback


class _PlanningTransitionBuilder:
    """Builds transitions and their grouped duration/condition/effect terms."""

    def __init__(
        self,
        base_url: str,
        context: _PlanningBuildContext,
        terms: _PlanningTermBuilder,
        build_action_parameters: Callable[[str, str, List[Dict[str, Any]]], Optional[model.SubmodelElementList]],
        normalize_named_transition_items: Callable[[Any], List[Dict[str, Any]]],
        normalize_transition_conditions: Callable[[Any], Dict[str, Dict[str, List[Dict[str, Any]]]]],
        normalize_transition_effects: Callable[[Any, str], Dict[str, Dict[str, List[Dict[str, Any]]]]],
    ):
        self._base_url = base_url
        self._context = context
        self._terms = terms
        self._build_action_parameters = build_action_parameters
        self._normalize_named_transition_items = normalize_named_transition_items
        self._normalize_transition_conditions = normalize_transition_conditions
        self._normalize_transition_effects = normalize_transition_effects

    def build_processes_section(self, system_id: str, processes_cfg: Any) -> model.SubmodelElementCollection:
        return self.build_transition_section(
            system_id=system_id,
            section_name="Processes",
            semantic_element="Process",
            items_cfg=processes_cfg,
            default_effect_group="ContinuousEffects",
            include_skill_reference=False,
            allow_duration=False,
        )

    def build_events_section(self, system_id: str, events_cfg: Any) -> model.SubmodelElementCollection:
        return self.build_transition_section(
            system_id=system_id,
            section_name="Events",
            semantic_element="Event",
            items_cfg=events_cfg,
            default_effect_group="EndEffects",
            include_skill_reference=False,
            allow_duration=False,
        )

    def build_actions_section(self, system_id: str, actions_cfg: Any) -> model.SubmodelElementCollection:
        return self.build_transition_section(
            system_id=system_id,
            section_name="Actions",
            semantic_element="Action",
            items_cfg=actions_cfg,
            default_effect_group="EndEffects",
            include_skill_reference=True,
            allow_duration=True,
        )

    def build_transition_section(
        self,
        system_id: str,
        section_name: str,
        semantic_element: str,
        items_cfg: Any,
        default_effect_group: str,
        include_skill_reference: bool,
        allow_duration: bool,
    ) -> model.SubmodelElementCollection:
        items = self._normalize_named_transition_items(items_cfg)
        elements: List[model.SubmodelElementCollection] = []

        for idx, item in enumerate(items):
            key = str(item.get("key") or f"{semantic_element}_{idx + 1}")
            normalized = self._normalize_transition_description(
                item=item,
                default_group=default_effect_group,
            )
            parameters = normalized.get("parameters", [])
            duration = normalized.get("duration", {}) if allow_duration else {}
            conditions = normalized.get("conditions", {})
            effects = normalized.get("effects", {})
            elements.append(
                self.build_transition_item(
                    system_id=system_id,
                    section_name=section_name,
                    key=key,
                    parameters=parameters,
                    conditions=conditions,
                    effects=effects,
                    item_semantic_id=SemanticIdCatalog.ai_planning_domain_section(semantic_element),
                    duration=duration,
                    skill_reference=item.get("SkillReference") if include_skill_reference else None,
                )
            )

        return model.SubmodelElementCollection(
            id_short=section_name,
            value=elements,
            semantic_id=_make_semantic_id(SemanticIdCatalog.ai_planning_domain_section(section_name)),
        )

    def _normalize_transition_description(
        self,
        item: Dict[str, Any],
        default_group: str,
    ) -> Dict[str, Any]:
        conditions_input = item.get("conditions")
        if conditions_input is None:
            conditions_input = item.get("precondition")

        effects_input = item.get("effects")
        if effects_input is None:
            effects_input = item.get("effect")

        normalized = normalize_description_from_pddl(
            {
                "parameters": item.get("parameters", []),
                "duration": item.get("duration"),
                "conditions": conditions_input,
                "effects": effects_input,
            },
            skill_name=str(item.get("key") or "transition"),
        )

        # Uncontrolled transitions may use section-specific default effect groups.
        normalized["effects"] = self._normalize_transition_effects(effects_input, default_group=default_group)
        normalized["parameters"] = normalize_parameters(item.get("parameters", []))
        return normalized

    def build_transition_item(
        self,
        system_id: str,
        section_name: str,
        key: str,
        parameters: List[Dict[str, Any]],
        conditions: Dict[str, Any],
        effects: Dict[str, Any],
        item_semantic_id: str,
        duration: Optional[Dict[str, Any]] = None,
        skill_reference: Optional[str] = None,
    ) -> model.SubmodelElementCollection:
        item_elements: List[model.SubmodelElement] = []

        self._context.section_parameter_names[(section_name, key)] = [
            str(param.get("name") or f"Parameter_{i}")
            for i, param in enumerate(parameters)
            if isinstance(param, dict)
        ]

        if skill_reference:
            item_elements.append(
                model.ReferenceElement(
                    id_short="SkillReference",
                    value=model.ModelReference(
                        key=(
                            model.Key(
                                type_=model.KeyTypes.SUBMODEL,
                                value=f"{self._base_url}/submodels/instances/{system_id}/Skills",
                            ),
                            model.Key(
                                type_=model.KeyTypes.SUBMODEL_ELEMENT_COLLECTION,
                                value=str(skill_reference),
                            ),
                        ),
                        type_=model.KeyTypes.SUBMODEL_ELEMENT_COLLECTION,
                    ),
                )
            )

        if parameters:
            parameter_element = self._build_action_parameters(system_id, key, parameters)
            if parameter_element is not None:
                item_elements.append(parameter_element)

        owner = _TermOwner(section=section_name, key=key)

        if duration:
            item_elements.append(
                self.build_duration_section(
                    system_id,
                    key,
                    duration,
                    term_owner=owner,
                )
            )

        if conditions:
            item_elements.append(
                self.build_conditions_section(
                    system_id,
                    key,
                    conditions,
                    term_owner=owner,
                )
            )

        if effects:
            item_elements.append(
                self.build_effects_section(
                    system_id,
                    key,
                    effects,
                    term_owner=owner,
                )
            )

        return model.SubmodelElementCollection(
            id_short=key,
            display_name=model.MultiLanguageNameType({"en": key}),
            value=item_elements,
            semantic_id=_make_semantic_id(item_semantic_id),
        )

    def build_duration_section(
        self,
        system_id: str,
        action_key: str,
        duration_cfg: Dict[str, Any],
        term_owner: Optional[_TermOwner] = None,
    ) -> model.SubmodelElementCollection:
        owner = self._terms.resolve_term_owner(term_owner, fallback_key=action_key)
        terms = duration_cfg.get("terms", []) or []
        elements = [
            self._terms.build_term(
                system_id,
                action_key,
                term,
                i + 1,
                is_effect=False,
                term_owner=owner,
            )
            for i, term in enumerate(terms)
        ]
        return model.SubmodelElementCollection(
            id_short="Duration",
            value=elements,
            semantic_id=_make_semantic_id(SemanticIdCatalog.PDDL_DURATION),
        )

    def build_conditions_section(
        self,
        system_id: str,
        action_key: str,
        conditions_cfg: Dict[str, Any],
        term_owner: Optional[_TermOwner] = None,
    ) -> model.SubmodelElementCollection:
        owner = self._terms.resolve_term_owner(term_owner, fallback_key=action_key)
        elements = self.build_grouped_terms(
            system_id=system_id,
            action_key=action_key,
            groups_cfg=conditions_cfg,
            group_names=("PreConditions", "InvariantConditions", "PostConditions"),
            term_owner=owner,
            is_effect=False,
            flatten_effect_terms=False,
        )

        return model.SubmodelElementCollection(
            id_short="Conditions",
            value=elements,
            semantic_id=_make_semantic_id(SemanticIdCatalog.PDDL_CONDITIONS),
        )

    def build_effects_section(
        self,
        system_id: str,
        action_key: str,
        effects_cfg: Dict[str, Any],
        term_owner: Optional[_TermOwner] = None,
    ) -> model.SubmodelElementCollection:
        owner = self._terms.resolve_term_owner(term_owner, fallback_key=action_key)
        elements = self.build_grouped_terms(
            system_id=system_id,
            action_key=action_key,
            groups_cfg=effects_cfg,
            group_names=("StartEffects", "ContinuousEffects", "EndEffects"),
            term_owner=owner,
            is_effect=True,
            flatten_effect_terms=True,
        )

        return model.SubmodelElementCollection(
            id_short="Effects",
            value=elements,
            semantic_id=_make_semantic_id(SemanticIdCatalog.PDDL_EFFECTS),
        )

    def build_grouped_terms(
        self,
        system_id: str,
        action_key: str,
        groups_cfg: Dict[str, Any],
        group_names: Tuple[str, ...],
        term_owner: _TermOwner,
        is_effect: bool,
        flatten_effect_terms: bool,
    ) -> List[model.SubmodelElementCollection]:
        elements: List[model.SubmodelElementCollection] = []
        for group_name in group_names:
            group = groups_cfg.get(group_name)
            if not isinstance(group, dict):
                continue
            terms = group.get("terms", []) or []
            if flatten_effect_terms:
                terms = [self._terms.flatten_effect_set(term) for term in terms]
            if not terms:
                continue
            elements.append(
                model.SubmodelElementCollection(
                    id_short=group_name,
                    value=[
                        self._terms.build_term(
                            system_id,
                            action_key,
                            term,
                            i + 1,
                            is_effect=is_effect,
                            term_owner=term_owner,
                        )
                        for i, term in enumerate(terms)
                    ],
                )
            )
        return elements

