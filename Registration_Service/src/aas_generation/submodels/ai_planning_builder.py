"""AI Planning Submodel builder facade.

Facade/orchestration class for AI planning submodel construction.
Collaborator implementations live in ai_planning_components.py.
"""

from typing import Any, Dict, List, Optional, Tuple

from basyx.aas import model

from ..semantic_ids import SemanticIdCatalog
from .ai_planning_components import (
    _DomainSectionBuilder,
    _PlanningBuildContext,
    _PlanningReferenceBuilder,
    _PlanningTermBuilder,
    _PlanningTransitionBuilder,
    _ProblemSectionBuilder,
    _TermOwner,
    _make_semantic_id,
)
from .skills_spec_parser import (
    CONDITION_GROUP_ALIASES,
    EFFECT_GROUP_ALIASES,
    normalize_description_from_pddl,
    normalize_section_groups,
    normalize_terms_payload,
)


class AIPlanningSubmodelBuilder:
    """Build AIPlanning submodel from `AI-Planning` config section."""

    SUBMODEL_SEMANTIC_ID = SemanticIdCatalog.AI_PLANNING_SUBMODEL

    def __init__(self, base_url: str):
        self.base_url = base_url
        self._context = _PlanningBuildContext()
        self._references = _PlanningReferenceBuilder(base_url=base_url, context=self._context)
        self._terms = _PlanningTermBuilder(
            references=self._references,
            typed_property_factory=self._typed_property,
        )
        self._transitions = _PlanningTransitionBuilder(
            base_url=base_url,
            context=self._context,
            terms=self._terms,
            build_action_parameters=self._build_action_parameters,
            normalize_named_transition_items=self._normalize_named_transition_items,
            normalize_transition_conditions=self._normalize_transition_conditions,
            normalize_transition_effects=self._normalize_transition_effects,
        )
        self._domain_builder = _DomainSectionBuilder(
            build_fluents_section=self._build_fluents_section,
            build_actions_section=self._build_actions_section,
            build_processes_section=self._build_processes_section,
            build_events_section=self._build_events_section,
            build_constraints_section=self._build_constraints_section,
        )
        self._problem_builder = _ProblemSectionBuilder(
            build_problem_objects_section=self._build_problem_objects_section,
            build_problem_state_section=self._build_problem_state_section,
            build_constraints_section=self._build_constraints_section,
            build_metric_section=self._build_metric_section,
        )

    def build(self, system_id: str, config: Dict[str, Any]) -> Optional[model.Submodel]:
        planning_cfg = config.get("AI-Planning") or {}
        if not isinstance(planning_cfg, dict) or not planning_cfg:
            return None

        self._context.reset()
        elements: List[model.SubmodelElement] = []

        domain_cfg = planning_cfg.get("Domain")
        if isinstance(domain_cfg, dict) and domain_cfg:
            elements.append(self._build_domain(system_id, domain_cfg))

        problem_cfg = planning_cfg.get("Problem")
        if isinstance(problem_cfg, dict) and problem_cfg:
            elements.append(self._build_problem(system_id, problem_cfg))

        if not elements:
            return None

        return model.Submodel(
            id_=f"{self.base_url}/submodels/instances/{system_id}/AIPlanning",
            id_short="AIPlanning",
            kind=model.ModellingKind.INSTANCE,
            semantic_id=_make_semantic_id(self.SUBMODEL_SEMANTIC_ID),
            administration=model.AdministrativeInformation(version="1", revision="0"),
            submodel_element=elements,
        )

    def _build_domain(self, system_id: str, domain_cfg: Dict[str, Any]) -> model.SubmodelElementCollection:
        return self._domain_builder.build(system_id=system_id, domain_cfg=domain_cfg)

    def _build_problem(self, system_id: str, problem_cfg: Dict[str, Any]) -> model.SubmodelElementCollection:
        return self._problem_builder.build(system_id=system_id, problem_cfg=problem_cfg)

    def _build_processes_section(
        self,
        system_id: str,
        processes_cfg: Any,
    ) -> model.SubmodelElementCollection:
        return self._transitions.build_processes_section(
            system_id=system_id,
            processes_cfg=processes_cfg,
        )

    def _build_events_section(
        self,
        system_id: str,
        events_cfg: Any,
    ) -> model.SubmodelElementCollection:
        return self._transitions.build_events_section(
            system_id=system_id,
            events_cfg=events_cfg,
        )

    def _build_transition_item(
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
        return self._transitions.build_transition_item(
            system_id=system_id,
            section_name=section_name,
            key=key,
            parameters=parameters,
            conditions=conditions,
            effects=effects,
            item_semantic_id=item_semantic_id,
            duration=duration,
            skill_reference=skill_reference,
        )

    def _normalize_named_transition_items(self, items_cfg: Any) -> List[Dict[str, Any]]:
        if isinstance(items_cfg, list):
            return [item for item in items_cfg if isinstance(item, dict)]

        if isinstance(items_cfg, dict):
            if any(k in items_cfg for k in ("key", "parameters", "conditions", "effects", "precondition", "effect")):
                return [items_cfg]
            items: List[Dict[str, Any]] = []
            for key, value in items_cfg.items():
                if isinstance(value, dict):
                    item = dict(value)
                    item.setdefault("key", str(key))
                    items.append(item)
            return items

        return []

    def _normalize_transition_conditions(self, raw_conditions: Any) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
        return self._normalize_transition_groups(
            groups_cfg=raw_conditions,
            aliases=CONDITION_GROUP_ALIASES,
            default_group="PreConditions",
        )

    def _normalize_transition_effects(
        self,
        raw_effects: Any,
        default_group: str,
    ) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
        aliases = dict(EFFECT_GROUP_ALIASES)
        aliases["effect"] = default_group
        return self._normalize_transition_groups(
            groups_cfg=raw_effects,
            aliases=aliases,
            default_group=default_group,
        )

    def _normalize_transition_groups(
        self,
        groups_cfg: Any,
        aliases: Dict[str, str],
        default_group: str,
    ) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
        """Normalize flexible section-group input into canonical grouped terms."""
        return normalize_section_groups(
            groups_cfg=groups_cfg,
            aliases=aliases,
            default_group=default_group,
        )

    def _build_constraints_section(
        self,
        system_id: str,
        section_name: str,
        constraints_cfg: Any,
        is_problem_section: bool,
    ) -> model.SubmodelElementCollection:
        terms = normalize_terms_payload(constraints_cfg)
        elements: List[model.SubmodelElement] = []
        for i, term in enumerate(terms):
            term_id_short = self._preferred_term_id_short(term, i + 1)
            elements.append(
                self._build_term(
                    system_id,
                    section_name,
                    term,
                    i + 1,
                    is_effect=False,
                    problem_section_name=section_name if is_problem_section else None,
                    id_short_override=term_id_short,
                )
            )
            if is_problem_section:
                self._register_preference_location(term, section_name, term_id_short)

        return model.SubmodelElementCollection(
            id_short=section_name,
            value=elements,
            semantic_id=_make_semantic_id(SemanticIdCatalog.ai_planning_section(section_name)),
        )

    def _build_metric_section(
        self,
        system_id: str,
        metric_cfg: Any,
    ) -> model.SubmodelElementCollection:
        optimization, expression = self._normalize_metric(metric_cfg)
        metric_elements: List[model.SubmodelElement] = [
            self._build_term(
                system_id,
                "Metric",
                term,
                i + 1,
                is_effect=False,
                problem_section_name="Metric",
            )
            for i, term in enumerate(expression)
        ]

        return model.SubmodelElementCollection(
            id_short="Metric",
            value=metric_elements,
            semantic_id=_make_semantic_id(SemanticIdCatalog.AI_PLANNING_PROBLEM_METRIC),
            qualifier=(
                model.Qualifier(
                    type_="Optimization",
                    value_type=model.datatypes.String,
                    value=optimization,
                ),
            ),
        )

    def _normalize_metric(self, metric_cfg: Any) -> Tuple[str, List[Dict[str, Any]]]:
        optimization = "minimize"
        payload = metric_cfg
        preference_weight_terms: List[Dict[str, Any]] = []

        if isinstance(metric_cfg, dict):
            if "minimize" in metric_cfg:
                optimization = "minimize"
                payload = metric_cfg.get("minimize")
            elif "maximize" in metric_cfg:
                optimization = "maximize"
                payload = metric_cfg.get("maximize")
            elif "optimize" in metric_cfg:
                opt_val = str(metric_cfg.get("optimize") or "").lower()
                optimization = "maximize" if opt_val == "maximize" else "minimize"
                payload = metric_cfg.get("expression") or metric_cfg.get("terms") or metric_cfg

            raw_weights = metric_cfg.get("preference_weights") or metric_cfg.get("preferences") or []
            if isinstance(raw_weights, list):
                preference_weight_terms = self._normalize_preference_weight_terms(raw_weights)

        expression_terms = normalize_terms_payload(payload)
        if preference_weight_terms:
            expression_terms.extend(preference_weight_terms)

        return optimization, expression_terms

    def _normalize_preference_weight_terms(self, raw_weights: List[Any]) -> List[Dict[str, Any]]:
        terms: List[Dict[str, Any]] = []
        for idx, item in enumerate(raw_weights):
            if not isinstance(item, dict):
                continue

            name = item.get("name") or item.get("preference") or item.get("id")
            if not name:
                continue

            weight_value = item.get("weight", 1)
            terms.append(
                {
                    "type": "arithmeticterm",
                    "semantic_id": SemanticIdCatalog.ARITHMETIC_SEMANTIC_IDS["*"],
                    "terms": [
                        {
                            "type": "function",
                            "PreferenceReference": str(name),
                            "parameters": [],
                        },
                        {
                            "type": "constant",
                            "name": f"PreferenceWeight_{idx + 1}",
                            "value": weight_value,
                        },
                    ],
                }
            )

        return terms

    def _build_problem_objects_section(
        self,
        system_id: str,
        objects_cfg: Any,
    ) -> model.SubmodelElementList:
        if not isinstance(objects_cfg, list):
            raise ValueError("Invalid AI-Planning Problem.Objects: expected a list")

        entries: List[model.ReferenceElement] = []
        names: List[str] = []

        for idx, obj in enumerate(objects_cfg):
            if not isinstance(obj, dict):
                raise ValueError(
                    f"Invalid AI-Planning Problem.Objects entry at index {idx}: expected object"
                )

            obj_name = str(obj.get("name") or f"Object_{idx}")
            model_ref = obj.get("ModelReference") or obj.get("modelRef")
            external_ref = obj.get("ExternalReference") or obj.get("externalRef")

            if external_ref and not model_ref:
                raise ValueError(
                    f"Invalid AI-Planning Problem.Objects entry '{obj_name}': external references are not allowed; use modelRef"
                )

            if not model_ref:
                raise ValueError(
                    f"Invalid AI-Planning Problem.Objects entry '{obj_name}': missing modelRef"
                )

            ref = self._build_model_reference_from_dsl(system_id, model_ref)
            entries.append(
                model.ReferenceElement(
                    id_short=None,
                    display_name=model.MultiLanguageNameType({"en": obj_name}),
                    value=ref,
                )
            )
            names.append(obj_name)

        self._context.problem_object_names = names
        return model.SubmodelElementList(
            id_short="Objects",
            value=entries,
            type_value_list_element=model.ReferenceElement,
            semantic_id=_make_semantic_id(SemanticIdCatalog.PDDL_OBJECTS),
            semantic_id_list_element=_make_semantic_id(SemanticIdCatalog.PDDL_OBJECT),
        )

    def _build_model_reference_from_dsl(self, system_id: str, model_ref: Any) -> model.ModelReference:
        return self._references.build_model_reference_from_dsl(system_id=system_id, model_ref=model_ref)

    def _build_fluents_section(self, fluents_cfg: List[Dict[str, Any]]) -> model.SubmodelElementCollection:
        fluent_elements: List[model.SubmodelElementCollection] = []

        for idx, fluent_cfg in enumerate(fluents_cfg):
            if not isinstance(fluent_cfg, dict):
                continue

            fluent_key = fluent_cfg.get("key") or f"Fluent_{idx + 1}"
            self._context.domain_fluents[fluent_key] = fluent_cfg
            elements: List[model.SubmodelElement] = []

            parameters = fluent_cfg.get("parameters", []) or []
            if isinstance(parameters, list) and parameters:
                parameter_element = self._build_domain_fluent_parameters(parameters)
                if parameter_element is not None:
                    elements.append(parameter_element)

            transformation = fluent_cfg.get("transformation")
            if transformation:
                elements.append(self._string_property("Transformation", transformation))

            semantic_id = fluent_cfg.get("semantic_id") or SemanticIdCatalog.PDDL_TERM
            fluent_elements.append(
                model.SubmodelElementCollection(
                    id_short=str(fluent_key),
                    display_name=model.MultiLanguageNameType({"en": str(fluent_key)}),
                    value=elements,
                    semantic_id=_make_semantic_id(semantic_id),
                    supplemental_semantic_id=[_make_semantic_id(SemanticIdCatalog.PDDL_TERM)]
                    if semantic_id != SemanticIdCatalog.PDDL_TERM
                    else [],
                )
            )

        return model.SubmodelElementCollection(
            id_short="Fluents",
            value=fluent_elements,
            semantic_id=_make_semantic_id(SemanticIdCatalog.AI_PLANNING_DOMAIN_FLUENTS),
        )

    def _build_actions_section(self, system_id: str, actions_cfg: List[Dict[str, Any]]) -> model.SubmodelElementCollection:
        action_elements: List[model.SubmodelElementCollection] = []

        for idx, action_cfg in enumerate(actions_cfg):
            if not isinstance(action_cfg, dict):
                continue

            action_key = action_cfg.get("key") or f"Action_{idx + 1}"
            normalized = normalize_description_from_pddl(action_cfg, skill_name=action_key)
            parameters = normalized.get("parameters", [])
            duration = normalized.get("duration", {})
            conditions = normalized.get("conditions", {})
            effects = normalized.get("effects", {})
            action_elements.append(
                self._build_transition_item(
                    system_id=system_id,
                    section_name="Actions",
                    key=str(action_key),
                    parameters=parameters,
                    conditions=conditions,
                    effects=effects,
                    duration=duration,
                    skill_reference=action_cfg.get("SkillReference"),
                    item_semantic_id=SemanticIdCatalog.AI_PLANNING_DOMAIN_ACTION,
                )
            )

        return model.SubmodelElementCollection(
            id_short="Actions",
            value=action_elements,
            semantic_id=_make_semantic_id(SemanticIdCatalog.AI_PLANNING_DOMAIN_ACTIONS),
        )

    def _build_domain_fluent_parameters(self, parameters: List[Dict[str, Any]]) -> Optional[model.SubmodelElementList]:
        entries: List[model.ReferenceElement] = []
        for idx, parameter in enumerate(parameters):
            if not isinstance(parameter, dict):
                continue

            name = parameter.get("name") or f"Parameter_{idx}"
            external = parameter.get("externalRef") or parameter.get("ExternalReference")
            if not external:
                continue

            entries.append(
                model.ReferenceElement(
                    id_short=None,
                    display_name=model.MultiLanguageNameType({"en": str(name)}),
                    value=model.ExternalReference(
                        key=(model.Key(model.KeyTypes.GLOBAL_REFERENCE, str(external)),)
                    ),
                )
            )

        if not entries:
            return None

        return model.SubmodelElementList(
            id_short="Parameters",
            value=entries,
            type_value_list_element=model.ReferenceElement,
            semantic_id=_make_semantic_id(SemanticIdCatalog.PDDL_PARAMETERS),
            semantic_id_list_element=_make_semantic_id(SemanticIdCatalog.PDDL_PARAMETER),
        )

    def _build_action_parameters(
        self,
        system_id: str,
        action_key: str,
        parameters: List[Dict[str, Any]],
    ) -> Optional[model.SubmodelElementList]:
        entries: List[model.ReferenceElement] = []

        for idx, parameter in enumerate(parameters):
            if not isinstance(parameter, dict):
                continue

            param_name = parameter.get("name") or f"Parameter_{idx}"
            ref: Optional[model.Reference] = None
            model_ref = parameter.get("ModelReference") or parameter.get("modelRef")
            external_ref = parameter.get("ExternalReference") or parameter.get("externalRef")

            if model_ref:
                ref = self._build_model_reference_from_dsl(system_id, model_ref)

            elif external_ref:
                ref = model.ExternalReference(
                    key=(model.Key(model.KeyTypes.GLOBAL_REFERENCE, str(external_ref)),)
                )

            if ref is not None:
                entries.append(
                    model.ReferenceElement(
                        id_short=None,
                        display_name=model.MultiLanguageNameType({"en": str(param_name)}),
                        value=ref,
                    )
                )

        if not entries:
            return None

        return model.SubmodelElementList(
            id_short="Parameters",
            value=entries,
            type_value_list_element=model.ReferenceElement,
            semantic_id=_make_semantic_id(SemanticIdCatalog.PDDL_PARAMETERS),
            semantic_id_list_element=_make_semantic_id(SemanticIdCatalog.PDDL_PARAMETER),
        )

    def _build_term(
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
        return self._terms.build_term(
            system_id=system_id,
            action_key=action_key,
            term_cfg=term_cfg,
            index=index,
            is_effect=is_effect,
            problem_section_name=problem_section_name,
            id_short_override=id_short_override,
            term_owner=term_owner,
        )

    def _build_problem_state_section(
        self,
        system_id: str,
        section_name: str,
        section_cfg: Any,
    ) -> model.SubmodelElementCollection:
        state_terms = normalize_terms_payload(section_cfg)
        elements: List[model.SubmodelElement] = []
        for i, term in enumerate(state_terms):
            term_id_short = self._preferred_term_id_short(term, i + 1)
            elements.append(
                self._build_term(
                    system_id,
                    f"{section_name}_state",
                    term,
                    i + 1,
                    is_effect=False,
                    problem_section_name=section_name,
                    id_short_override=term_id_short,
                )
            )
            if section_name == "Goal":
                self._register_preference_location(term, section_name, term_id_short)

        return model.SubmodelElementCollection(
            id_short=section_name,
            value=elements,
            semantic_id=_make_semantic_id(SemanticIdCatalog.ai_planning_problem_section(section_name)),
        )

    def _preferred_term_id_short(self, term_cfg: Dict[str, Any], index: int) -> str:
        return f"term_{index}"

    def _extract_preference_name(self, term_cfg: Any) -> Optional[str]:
        if not isinstance(term_cfg, dict):
            return None
        term_type = str(term_cfg.get("type", "")).lower()
        semantic_id = str(term_cfg.get("semantic_id", "")).lower()
        if term_type == "temporalterm" and "preference" in semantic_id and term_cfg.get("name"):
            return str(term_cfg.get("name"))
        return None

    def _register_preference_location(
        self,
        term_cfg: Dict[str, Any],
        section_name: str,
        term_id_short: str,
    ) -> None:
        pref_name = self._extract_preference_name(term_cfg)
        if not pref_name:
            return
        existing = self._context.problem_preference_locations.get(pref_name)
        if existing and existing != (section_name, term_id_short):
            raise ValueError(
                f"Duplicate preference name '{pref_name}' in Problem section. Preference names must be unique."
            )
        self._context.problem_preference_locations[pref_name] = (section_name, term_id_short)

    def _string_property(self, id_short: str, value: str) -> model.Property:
        return model.Property(
            id_short=id_short,
            value_type=model.datatypes.String,
            value=str(value),
        )

    def _typed_property(self, id_short: str, value: Any, display_name: Optional[str] = None) -> model.Property:
        if isinstance(value, bool):
            value_type = model.datatypes.Boolean
            val = value
        elif isinstance(value, int):
            value_type = model.datatypes.Integer
            val = value
        elif isinstance(value, float):
            value_type = model.datatypes.Double
            val = value
        else:
            value_type = model.datatypes.String
            val = str(value)

        if display_name:
            return model.Property(
                id_short=id_short,
                value_type=value_type,
                value=val,
                display_name=model.MultiLanguageNameType({"en": display_name}),
            )

        return model.Property(id_short=id_short, value_type=value_type, value=val)

