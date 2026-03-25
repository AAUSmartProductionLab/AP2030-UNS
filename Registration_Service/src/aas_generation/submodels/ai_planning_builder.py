"""AI Planning Submodel builder.

This submodel stores planning-relevant information separate from Skills.
Both Domain and Problem sections are optional and can coexist in the same
submodel instance.
"""

from typing import Any, Dict, List, Optional, Tuple

from basyx.aas import model

from .skills_spec_parser import normalize_description_from_pddl


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


class AIPlanningSubmodelBuilder:
    """Build AIPlanning submodel from `AI-Planning` config section."""

    SUBMODEL_SEMANTIC_ID = "https://smartproductionlab.aau.dk/submodels/AIPlanning/1/0"

    def __init__(self, base_url: str):
        self.base_url = base_url
        self._domain_fluents: Dict[str, Dict[str, Any]] = {}
        self._action_parameter_names: Dict[str, List[str]] = {}

    def build(self, system_id: str, config: Dict[str, Any]) -> Optional[model.Submodel]:
        planning_cfg = config.get("AI-Planning") or {}
        if not isinstance(planning_cfg, dict) or not planning_cfg:
            return None

        self._domain_fluents = {}
        self._action_parameter_names = {}
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
        elements: List[model.SubmodelElement] = []

        fluents_cfg = domain_cfg.get("Fluents", []) or []
        if isinstance(fluents_cfg, list) and fluents_cfg:
            elements.append(self._build_fluents_section(fluents_cfg))

        actions_cfg = domain_cfg.get("Actions", []) or []
        if isinstance(actions_cfg, list) and actions_cfg:
            elements.append(self._build_actions_section(system_id, actions_cfg))

        for section_name in ("Processes", "Events", "Constraints"):
            section_cfg = domain_cfg.get(section_name)
            if section_cfg:
                elements.append(self._build_freeform_section(section_name, section_cfg))

        return model.SubmodelElementCollection(
            id_short="Domain",
            value=elements,
            semantic_id=_make_semantic_id("https://smartproductionlab.aau.dk/AIPlanning/Domain"),
        )

    def _build_problem(self, system_id: str, problem_cfg: Dict[str, Any]) -> model.SubmodelElementCollection:
        elements: List[model.SubmodelElement] = []

        objects_cfg = problem_cfg.get("Objects")
        if objects_cfg:
            elements.append(self._build_freeform_section("Objects", objects_cfg))

        initial_state = problem_cfg.get("Init")
        if initial_state:
            elements.append(self._build_problem_state_section(system_id, "Init", initial_state))

        goal_state = problem_cfg.get("Goal")
        if goal_state:
            elements.append(self._build_problem_state_section(system_id, "Goal", goal_state))

        metric_cfg = problem_cfg.get("Metric")
        if metric_cfg:
            elements.append(self._build_freeform_section("Metric", metric_cfg))

        preferences_cfg = problem_cfg.get("Preferences")
        if preferences_cfg:
            elements.append(self._build_freeform_section("Preferences", preferences_cfg))

        return model.SubmodelElementCollection(
            id_short="Problem",
            value=elements,
            semantic_id=_make_semantic_id("https://smartproductionlab.aau.dk/AIPlanning/Problem"),
        )

    def _build_fluents_section(self, fluents_cfg: List[Dict[str, Any]]) -> model.SubmodelElementCollection:
        fluent_elements: List[model.SubmodelElementCollection] = []

        for idx, fluent_cfg in enumerate(fluents_cfg):
            if not isinstance(fluent_cfg, dict):
                continue

            fluent_key = fluent_cfg.get("key") or f"Fluent_{idx + 1}"
            self._domain_fluents[fluent_key] = fluent_cfg
            elements: List[model.SubmodelElement] = []

            parameters = fluent_cfg.get("parameters", []) or []
            if isinstance(parameters, list) and parameters:
                elements.append(self._build_domain_fluent_parameters(parameters))

            transformation = fluent_cfg.get("transformation")
            if transformation:
                elements.append(self._string_property("Transformation", transformation))

            semantic_id = fluent_cfg.get("semantic_id") or "https://smartproductionlab.aau.dk/PDDL/Term"
            fluent_elements.append(
                model.SubmodelElementCollection(
                    id_short=str(fluent_key),
                    display_name=model.MultiLanguageNameType({"en": str(fluent_key)}),
                    value=elements,
                    semantic_id=_make_semantic_id(semantic_id),
                    supplemental_semantic_id=[_make_semantic_id("https://smartproductionlab.aau.dk/PDDL/Term")]
                    if semantic_id != "https://smartproductionlab.aau.dk/PDDL/Term"
                    else [],
                )
            )

        return model.SubmodelElementCollection(
            id_short="Fluents",
            value=fluent_elements,
            semantic_id=_make_semantic_id("https://smartproductionlab.aau.dk/AIPlanning/Domain/Fluents"),
        )

    def _build_actions_section(self, system_id: str, actions_cfg: List[Dict[str, Any]]) -> model.SubmodelElementCollection:
        action_elements: List[model.SubmodelElementCollection] = []

        for idx, action_cfg in enumerate(actions_cfg):
            if not isinstance(action_cfg, dict):
                continue

            action_key = action_cfg.get("key") or f"Action_{idx + 1}"
            normalized = normalize_description_from_pddl(action_cfg, skill_name=action_key)
            elements: List[model.SubmodelElement] = []

            skill_ref = action_cfg.get("SkillReference")
            if skill_ref:
                elements.append(
                    model.ReferenceElement(
                        id_short="SkillReference",
                        value=model.ModelReference(
                            key=(
                                model.Key(
                                    type_=model.KeyTypes.SUBMODEL,
                                    value=f"{self.base_url}/submodels/instances/{system_id}/Skills",
                                ),
                                model.Key(
                                    type_=model.KeyTypes.SUBMODEL_ELEMENT_COLLECTION,
                                    value=str(skill_ref),
                                ),
                            ),
                            type_=model.KeyTypes.SUBMODEL_ELEMENT_COLLECTION,
                        ),
                    )
                )

            parameters = normalized.get("parameters", [])
            self._action_parameter_names[str(action_key)] = [
                str(param.get("name") or f"Parameter_{i}")
                for i, param in enumerate(parameters)
                if isinstance(param, dict)
            ]
            if parameters:
                elements.append(self._build_action_parameters(system_id, action_key, parameters))

            duration = normalized.get("duration", {})
            if duration:
                elements.append(self._build_duration_section(system_id, action_key, duration))

            conditions = normalized.get("conditions", {})
            if conditions:
                elements.append(self._build_conditions_section(system_id, action_key, conditions))

            effects = normalized.get("effects", {})
            if effects:
                elements.append(self._build_effects_section(system_id, action_key, effects))

            action_elements.append(
                model.SubmodelElementCollection(
                    id_short=str(action_key),
                    display_name=model.MultiLanguageNameType({"en": str(action_key)}),
                    value=elements,
                    semantic_id=_make_semantic_id("https://smartproductionlab.aau.dk/AIPlanning/Domain/Action"),
                )
            )

        return model.SubmodelElementCollection(
            id_short="Actions",
            value=action_elements,
            semantic_id=_make_semantic_id("https://smartproductionlab.aau.dk/AIPlanning/Domain/Actions"),
        )

    def _build_domain_fluent_parameters(self, parameters: List[Dict[str, Any]]) -> model.SubmodelElementList:
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

        return model.SubmodelElementList(
            id_short="Parameters",
            value=entries,
            type_value_list_element=model.ReferenceElement,
            semantic_id=_make_semantic_id("https://smartproductionlab.aau.dk/PDDL/Parameters"),
            semantic_id_list_element=_make_semantic_id("https://smartproductionlab.aau.dk/PDDL/Parameter"),
        )

    def _build_action_parameters(
        self,
        system_id: str,
        action_key: str,
        parameters: List[Dict[str, Any]],
    ) -> model.SubmodelElementList:
        entries: List[model.ReferenceElement] = []

        for idx, parameter in enumerate(parameters):
            if not isinstance(parameter, dict):
                continue

            param_name = parameter.get("name") or f"Parameter_{idx}"
            ref: Optional[model.Reference] = None
            model_ref = parameter.get("ModelReference") or parameter.get("modelRef")
            external_ref = parameter.get("ExternalReference") or parameter.get("externalRef")

            if model_ref:
                keys: List[model.Key] = []
                last_type = model.KeyTypes.REFERENCE_ELEMENT
                for part in model_ref:
                    if not isinstance(part, dict):
                        continue
                    k, v = next(iter(part.items()))
                    if k == "AAS":
                        last_type = model.KeyTypes.ASSET_ADMINISTRATION_SHELL
                        if v == "self":
                            v = f"{self.base_url}/aas/{system_id}"
                    elif k == "SM":
                        last_type = model.KeyTypes.SUBMODEL
                        v = f"{self.base_url}/submodels/instances/{system_id}/{v}"
                    elif k == "SMC":
                        last_type = model.KeyTypes.SUBMODEL_ELEMENT_COLLECTION
                    elif k == "SML":
                        last_type = model.KeyTypes.SUBMODEL_ELEMENT_LIST
                    elif k == "ReferenceElement":
                        last_type = model.KeyTypes.REFERENCE_ELEMENT
                    elif k == "Property":
                        last_type = model.KeyTypes.PROPERTY
                    keys.append(model.Key(last_type, str(v)))

                if keys:
                    ref = model.ModelReference(key=tuple(keys), type_=last_type)

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

        return model.SubmodelElementList(
            id_short="Parameters",
            value=entries,
            type_value_list_element=model.ReferenceElement,
            semantic_id=_make_semantic_id("https://smartproductionlab.aau.dk/PDDL/Parameters"),
            semantic_id_list_element=_make_semantic_id("https://smartproductionlab.aau.dk/PDDL/Parameter"),
        )

    def _build_duration_section(
        self,
        system_id: str,
        action_key: str,
        duration_cfg: Dict[str, Any],
    ) -> model.SubmodelElementCollection:
        terms = duration_cfg.get("terms", []) or []
        elements = [self._build_term(system_id, action_key, term, i + 1, is_effect=False) for i, term in enumerate(terms)]
        return model.SubmodelElementCollection(
            id_short="Duration",
            value=elements,
            semantic_id=_make_semantic_id("https://smartproductionlab.aau.dk/PDDL/Duration"),
        )

    def _build_conditions_section(
        self,
        system_id: str,
        action_key: str,
        conditions_cfg: Dict[str, Any],
    ) -> model.SubmodelElementCollection:
        elements: List[model.SubmodelElementCollection] = []
        for group_name in ("PreConditions", "InvariantConditions", "PostConditions"):
            group = conditions_cfg.get(group_name)
            if not isinstance(group, dict):
                continue
            terms = group.get("terms", []) or []
            if not terms:
                continue
            elements.append(
                model.SubmodelElementCollection(
                    id_short=group_name,
                    value=[
                        self._build_term(system_id, action_key, term, i + 1, is_effect=False)
                        for i, term in enumerate(terms)
                    ],
                )
            )

        return model.SubmodelElementCollection(
            id_short="Conditions",
            value=elements,
            semantic_id=_make_semantic_id("https://smartproductionlab.aau.dk/PDDL/Conditions"),
        )

    def _build_effects_section(
        self,
        system_id: str,
        action_key: str,
        effects_cfg: Dict[str, Any],
    ) -> model.SubmodelElementCollection:
        elements: List[model.SubmodelElementCollection] = []
        for group_name in ("StartEffects", "ContinuousEffects", "EndEffects"):
            group = effects_cfg.get(group_name)
            if not isinstance(group, dict):
                continue
            raw_terms = group.get("terms", []) or []
            terms = [self._flatten_effect_set(term) for term in raw_terms]
            if not terms:
                continue
            elements.append(
                model.SubmodelElementCollection(
                    id_short=group_name,
                    value=[
                        self._build_term(system_id, action_key, term, i + 1, is_effect=True)
                        for i, term in enumerate(terms)
                    ],
                )
            )

        return model.SubmodelElementCollection(
            id_short="Effects",
            value=elements,
            semantic_id=_make_semantic_id("https://smartproductionlab.aau.dk/PDDL/Effects"),
        )

    def _build_term(
        self,
        system_id: str,
        action_key: str,
        term_cfg: Dict[str, Any],
        index: int,
        is_effect: bool,
    ) -> model.SubmodelElementCollection:
        term_type = term_cfg.get("type")
        if term_type in {"predicate", "function", "fluent"}:
            return self._build_action_fluent(system_id, action_key, term_cfg)

        if term_type == "constant":
            literal = self._build_constant_property(term_cfg, index)
            return model.SubmodelElementCollection(
                id_short=f"Constant_{index}",
                value=[literal],
                semantic_id=_make_semantic_id("https://smartproductionlab.aau.dk/PDDL/Term"),
            )

        semantic_id_str = term_cfg.get("semantic_id")
        display_name = _semantic_id_display_name(semantic_id_str) or (term_type or f"Term_{index}")

        child_terms = term_cfg.get("terms", []) or []
        term_elements: List[model.SubmodelElement] = []
        constant_properties: List[model.Property] = []

        for i, child in enumerate(child_terms):
            child_type = child.get("type") or child.get("key")
            if child_type == "constant":
                constant_properties.append(self._build_constant_property(child, len(constant_properties) + 1))
            else:
                term_elements.append(self._build_term(system_id, action_key, child, i + 1, is_effect=is_effect))

        if constant_properties:
            term_elements.append(
                model.SubmodelElementCollection(
                    id_short="Constants",
                    value=constant_properties,
                    semantic_id=_make_semantic_id("https://smartproductionlab.aau.dk/PDDL/Term/Constants"),
                )
            )

        return model.SubmodelElementCollection(
            id_short=f"Term_{index}",
            value=term_elements,
            semantic_id=_make_semantic_id("https://smartproductionlab.aau.dk/PDDL/Term"),
            supplemental_semantic_id=[_make_semantic_id(semantic_id_str)] if semantic_id_str else [],
            display_name=model.MultiLanguageNameType({"en": display_name}),
        )

    def _build_action_fluent(
        self,
        system_id: str,
        action_key: str,
        fluent_cfg: Dict[str, Any],
        resolve_parameter_refs: bool = True,
    ) -> model.SubmodelElementCollection:
        elements: List[model.SubmodelElement] = []

        ref_name = fluent_cfg.get("TransformationReference")
        external_ref = fluent_cfg.get("ExternalReference")
        inferred_semantic_id = fluent_cfg.get("semantic_id")

        if ref_name:
            domain_fluent = self._domain_fluents.get(str(ref_name), {})
            inferred_semantic_id = inferred_semantic_id or domain_fluent.get("semantic_id")
            elements.append(
                model.ReferenceElement(
                    id_short="FluentReference",
                    value=model.ModelReference(
                        key=(
                            model.Key(
                                type_=model.KeyTypes.SUBMODEL,
                                value=f"{self.base_url}/submodels/instances/{system_id}/AIPlanning",
                            ),
                            model.Key(
                                type_=model.KeyTypes.SUBMODEL_ELEMENT_COLLECTION,
                                value="Domain",
                            ),
                            model.Key(
                                type_=model.KeyTypes.SUBMODEL_ELEMENT_COLLECTION,
                                value="Fluents",
                            ),
                            model.Key(
                                type_=model.KeyTypes.SUBMODEL_ELEMENT_COLLECTION,
                                value=str(ref_name),
                            ),
                        ),
                        type_=model.KeyTypes.SUBMODEL_ELEMENT_COLLECTION,
                    ),
                )
            )
        elif external_ref:
            inferred_semantic_id = inferred_semantic_id or external_ref
            elements.append(
                model.ReferenceElement(
                    id_short="FluentReference",
                    value=model.ExternalReference(
                        key=(model.Key(model.KeyTypes.GLOBAL_REFERENCE, str(external_ref)),)
                    ),
                )
            )

        args = fluent_cfg.get("parameters", []) or []
        if resolve_parameter_refs:
            parameter_refs = [
                self._build_action_parameter_reference(system_id, action_key, int(arg))
                for arg in args
                if isinstance(arg, int)
            ]
            elements.append(
                model.SubmodelElementList(
                    id_short="Parameters",
                    type_value_list_element=model.ReferenceElement,
                    value=parameter_refs,
                    semantic_id_list_element=_make_semantic_id("https://smartproductionlab.aau.dk/PDDL/Parameter"),
                )
            )
        else:
            literal_args = [
                self._typed_property(f"Argument_{idx + 1:02d}", arg)
                for idx, arg in enumerate(args)
            ]
            elements.append(
                model.SubmodelElementCollection(
                    id_short="Parameters",
                    value=literal_args,
                    semantic_id=_make_semantic_id("https://smartproductionlab.aau.dk/PDDL/Parameters"),
                )
            )

        if "value" in fluent_cfg and self._should_emit_numeric_value(fluent_cfg):
            elements.append(self._typed_property("Value", fluent_cfg.get("value")))

        semantic_name = _semantic_id_tail(inferred_semantic_id)
        id_short = str(ref_name or semantic_name or "Fluent")

        supp_ids = []
        pred_sid = _make_semantic_id(inferred_semantic_id)
        if pred_sid:
            supp_ids.append(pred_sid)

        return model.SubmodelElementCollection(
            id_short=id_short,
            value=elements,
            display_name=model.MultiLanguageNameType({"en": id_short}),
            semantic_id=pred_sid or _make_semantic_id("https://smartproductionlab.aau.dk/PDDL/Term"),
            supplemental_semantic_id=[_make_semantic_id("https://smartproductionlab.aau.dk/PDDL/Term")] + supp_ids
            if pred_sid
            else [],
        )

    def _build_action_parameter_reference(
        self,
        system_id: str,
        action_key: str,
        param_idx: int,
    ) -> model.ReferenceElement:
        parameter_names = self._action_parameter_names.get(str(action_key), [])
        display_name = (
            parameter_names[param_idx]
            if 0 <= param_idx < len(parameter_names)
            else f"Parameter_{param_idx}"
        )

        return model.ReferenceElement(
            id_short=None,
            display_name=model.MultiLanguageNameType({"en": display_name}),
            value=model.ModelReference(
                key=(
                    model.Key(
                        type_=model.KeyTypes.SUBMODEL,
                        value=f"{self.base_url}/submodels/instances/{system_id}/AIPlanning",
                    ),
                    model.Key(
                        type_=model.KeyTypes.SUBMODEL_ELEMENT_COLLECTION,
                        value="Domain",
                    ),
                    model.Key(
                        type_=model.KeyTypes.SUBMODEL_ELEMENT_COLLECTION,
                        value="Actions",
                    ),
                    model.Key(
                        type_=model.KeyTypes.SUBMODEL_ELEMENT_COLLECTION,
                        value=str(action_key),
                    ),
                    model.Key(
                        type_=model.KeyTypes.SUBMODEL_ELEMENT_LIST,
                        value="Parameters",
                    ),
                    model.Key(
                        type_=model.KeyTypes.REFERENCE_ELEMENT,
                        value=str(param_idx),
                    ),
                ),
                type_=model.KeyTypes.REFERENCE_ELEMENT,
            ),
        )

    def _build_problem_state_section(
        self,
        system_id: str,
        section_name: str,
        section_cfg: Any,
    ) -> model.SubmodelElementCollection:
        state_terms = self._normalize_problem_state_terms(section_cfg)
        elements = [
            self._build_action_fluent(system_id, f"{section_name}_state", term, resolve_parameter_refs=False)
            if (term.get("type") in {"predicate", "function", "fluent"})
            else self._build_term(system_id, f"{section_name}_state", term, i + 1, is_effect=False)
            for i, term in enumerate(state_terms)
        ]

        return model.SubmodelElementCollection(
            id_short=section_name,
            value=elements,
            semantic_id=_make_semantic_id(f"https://smartproductionlab.aau.dk/AIPlanning/Problem/{section_name}"),
        )

    def _normalize_problem_state_terms(self, section_cfg: Any) -> List[Dict[str, Any]]:
        if not isinstance(section_cfg, list):
            return []

        terms: List[Dict[str, Any]] = []
        for entry in section_cfg:
            if not isinstance(entry, dict):
                continue

            if "pred" in entry:
                term = self._normalize_problem_predicate(entry["pred"])
                if term:
                    terms.append(term)
                continue

            if "not" in entry:
                neg_payload = entry["not"]
                if isinstance(neg_payload, list) and neg_payload and isinstance(neg_payload[0], dict) and "pred" in neg_payload[0]:
                    term = self._normalize_problem_predicate(neg_payload[0]["pred"])
                    if term:
                        terms.append(
                            {
                                "type": "logicalterm",
                                "semantic_id": "https://smartproductionlab.aau.dk/PDDL/Term/Logic/Not",
                                "terms": [term],
                            }
                        )
                    continue
                if isinstance(neg_payload, dict) and "pred" in neg_payload:
                    term = self._normalize_problem_predicate(neg_payload["pred"])
                    if term:
                        terms.append(
                            {
                                "type": "logicalterm",
                                "semantic_id": self.SUBMODEL_SEMANTIC_ID.LOGIC_SEMANTIC_IDS,
                                "terms": [term],
                            }
                        )
                    continue

        return terms

    def _normalize_problem_predicate(self, payload: Any) -> Optional[Dict[str, Any]]:
        if isinstance(payload, str):
            return {
                "type": "predicate",
                "TransformationReference": payload,
                "parameters": [],
            }

        if not isinstance(payload, dict):
            return None

        return {
            "type": "predicate",
            "TransformationReference": payload.get("ref"),
            "ExternalReference": payload.get("external") or payload.get("externalRef"),
            "parameters": payload.get("args") or payload.get("parameters") or [],
            "semantic_id": payload.get("semantic_id") or payload.get("semanticId"),
        }

    def _flatten_effect_set(self, term_cfg: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(term_cfg, dict):
            return term_cfg

        semantic_id = str(term_cfg.get("semantic_id", "")).lower()
        if term_cfg.get("type") == "arithmeticterm" and semantic_id.endswith("/set"):
            fluent_term, value_term = self._extract_set_parts(term_cfg.get("terms", []) or [])
            if fluent_term is not None:
                if value_term is not None:
                    fluent_term = dict(fluent_term)
                    fluent_term["value"] = value_term
                return fluent_term

        children = term_cfg.get("terms")
        if isinstance(children, list):
            updated = [self._flatten_effect_set(child) if isinstance(child, dict) else child for child in children]
            flattened = dict(term_cfg)
            flattened["terms"] = updated
            return flattened

        return term_cfg

    def _should_emit_numeric_value(self, fluent_cfg: Dict[str, Any]) -> bool:
        value = fluent_cfg.get("value")
        if isinstance(value, bool):
            return False

        term_type = str(fluent_cfg.get("type", "")).lower()
        if term_type == "function":
            return True

        return isinstance(value, (int, float))

    def _extract_set_parts(self, terms: List[Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], Optional[Any]]:
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

    def _build_constant_property(self, term_cfg: Dict[str, Any], index: int) -> model.Property:
        const_name = term_cfg.get("name") or f"Constant_{index}"
        return self._typed_property(const_name, term_cfg.get("value"))

    def _build_freeform_section(self, section_name: str, section_cfg: Any) -> model.SubmodelElementCollection:
        return model.SubmodelElementCollection(
            id_short=section_name,
            value=[self._string_property("Payload", str(section_cfg))],
            semantic_id=_make_semantic_id(f"https://smartproductionlab.aau.dk/AIPlanning/{section_name}"),
        )

    def _string_property(self, id_short: str, value: str) -> model.Property:
        return model.Property(
            id_short=id_short,
            value_type=model.datatypes.String,
            value=str(value),
        )

    def _typed_property(self, id_short: str, value: Any) -> model.Property:
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

        return model.Property(id_short=id_short, value_type=value_type, value=val)
