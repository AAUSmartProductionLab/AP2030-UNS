"""Skills Submodel Builder for AAS generation."""

from typing import Dict, List, Optional
from basyx.aas import model


class SkillsSubmodelBuilder:
    """
    Builder class for creating Skills submodel.

    The Skills submodel contains Operations derived from action interfaces,
    each wrapped in a SubmodelElementCollection with interface references.
    """

    def __init__(self, base_url: str, delegation_base_url: Optional[str],
                 semantic_factory, element_factory, schema_handler):
        """
        Initialize the Skills submodel builder.

        Args:
            base_url: Base URL for AAS identifiers
            delegation_base_url: Base URL for operation delegation service
            semantic_factory: SemanticIdFactory instance for semantic IDs
            element_factory: AASElementFactory instance for element creation
            schema_handler: SchemaHandler instance for schema processing
        """
        self.base_url = base_url
        self.delegation_base_url = delegation_base_url
        self.semantic_factory = semantic_factory
        self.element_factory = element_factory
        self.schema_handler = schema_handler

    def build(self, system_id: str, config: Dict) -> model.Submodel:
        """
        Create the Skills submodel with Operations derived from action interfaces.

        Each operation is wrapped in a SubmodelElementCollection that also contains
        a reference to its corresponding action interface.

        The operations are generated from:
        - Explicit Skills configuration in YAML (if provided)
        - OR automatically from action interfaces in AssetInterfacesDescription

        Args:
            system_id: Unique identifier for the system
            config: Configuration dictionary

        Returns:
            Skills submodel with Operations wrapped in SubmodelElementCollections
        """
        skills_config = config.get('Skills', {}) or {}
        skill_elements = []

        # Get action interfaces from AssetInterfacesDescription
        interface_config = config.get('AssetInterfacesDescription', {}) or {}
        mqtt_config = interface_config.get('InterfaceMQTT', {}) or {}
        interaction_metadata = mqtt_config.get('InteractionMetadata', {}) or {}
        actions = interaction_metadata.get('actions', {}) or {}

        # Actions is already a dict with action names as keys
        action_map = actions

        # If explicit Skills are configured, use them
        if skills_config:
            for skill_name, skill_data in skills_config.items():
                skill_collection = self._create_skill_collection(
                    skill_name, skill_data, action_map, system_id
                )
                if skill_collection:
                    skill_elements.append(skill_collection)

        # Create submodel
        submodel = model.Submodel(
            id_=f"{self.base_url}/submodels/instances/{system_id}/Skills",
            id_short="Skills",
            kind=model.ModellingKind.INSTANCE,
            semantic_id=self.semantic_factory.SKILLS_SUBMODEL,
            administration=model.AdministrativeInformation(
                version="1", revision="0"),
            submodel_element=skill_elements
        )

        return submodel

    def _create_skill_collection(self, skill_name: str, skill_data: Dict,
                                 action_map: Dict, system_id: str) -> Optional[model.SubmodelElementCollection]:
        """
        Create a skill collection with operation and interface reference.

        Args:
            skill_name: Name of the skill
            skill_data: Configuration for the skill
            action_map: Map of action names to action configs
            system_id: System identifier

        Returns:
            SubmodelElementCollection containing the skill operation
        """
        # Get the interface name for this skill
        interface_ref_raw = skill_data.get('InterfaceReference', skill_name)
        # Handle InterfaceReference as either a string or a dict with Name key
        if isinstance(interface_ref_raw, dict):
            interface_name = interface_ref_raw.get('Name', skill_name)
        else:
            interface_name = interface_ref_raw
        elements = []
        is_async = False

        # Create the Operation from the linked action interface
        if interface_name and interface_name in action_map:
            action_config = action_map[interface_name]
            operation = self._create_operation_from_action(
                skill_name, action_config, system_id
            )
            elements.append(operation)

            # Determine if this is an asynchronous operation
            is_async = self._is_async_operation(action_config)

            # Create reference to the action interface
            interface_reference = self._create_interface_reference(
                interface_name, system_id)
            elements.append(interface_reference)

        elif 'input_variable' in skill_data or 'output_variable' in skill_data:
            # Fallback: create operation from explicit skill config
            operation = self._create_operation_from_config(
                skill_name, skill_data, system_id)
            elements.append(operation)

        if not elements:
            return None

        # For asynchronous operations, add an StateMachine property
        # This property can be polled by clients for intermediate state updates
        if is_async:
            state_property = self._create_state_machine_property()
            elements.append(state_property)

        # Build PDDL skill description if present in YAML config
        skill_desc_config = skill_data.get('skill_desription')
        if skill_desc_config:
            skill_desc_smc = self._build_skill_description(skill_desc_config, system_id)
            elements.append(skill_desc_smc)

        # Wrap operation and reference in a SubmodelElementCollection
        return self.element_factory.create_collection(
            id_short=skill_name,
            elements=elements,
            description=skill_data.get('description', f'Skill: {skill_name}')
        )

    def _create_operation_from_action(self, action_name: str, action_config: Dict,
                                      system_id: str) -> model.Operation:
        """
        Create an operation from an action interface configuration.

        Args:
            action_name: Name of the action
            action_config: Action configuration from AssetInterfacesDescription
            system_id: System identifier

        Returns:
            Operation element
        """
        input_variables = []
        output_variables = []
        inoutput_variables = []

        # Track property names to avoid duplicates between input and output
        input_prop_names = set()

        # Parse input schema if present - expand arrays into individual variables
        input_schema_url = action_config.get('input')
        if input_schema_url:
            schema = self.schema_handler.load_schema(input_schema_url)
            if schema:
                # Use extract_operation_variables to expand arrays (e.g., Position -> X, Y, Theta)
                vars = self.schema_handler.extract_operation_variables(schema)
                for var_name, var_info in vars.items():
                    var_type = var_info.get('type', 'string')
                    var_desc = var_info.get('description', '')
                    
                    input_variables.append(
                        self._create_operation_variable(
                            var_name, var_type, var_desc)
                    )
                    input_prop_names.add(var_name)

        # Parse output schema if present - expand arrays into individual variables
        output_schema_url = action_config.get('output')
        if output_schema_url:
            schema = self.schema_handler.load_schema(output_schema_url)
            if schema:
                # Use extract_operation_variables to expand arrays
                vars = self.schema_handler.extract_operation_variables(schema)
                for var_name, var_info in vars.items():
                    var_type = var_info.get('type', 'string')
                    var_desc = var_info.get('description', '')

                    # If property exists in both input and output, it becomes in-output
                    if var_name in input_prop_names:
                        # Move from input to in-output
                        inoutput_variables.append(
                            self._create_operation_variable(
                                var_name, var_type, var_desc)
                        )
                        # Remove from input_variables
                        input_variables = [
                            v for v in input_variables if v.id_short != var_name]
                    else:
                        output_variables.append(
                            self._create_operation_variable(
                                var_name, var_type, var_desc)
                        )

        # Get description from action title or key
        description = action_config.get('title', action_name)

        # Create semantic ID from action name
        semantic_id = self.semantic_factory.create_skill_semantic_id(
            action_name)

        # Build the qualifiers for the operation
        qualifiers = self._create_operation_qualifiers(
            action_config, system_id, action_name)

        # Use element factory to create the operation
        return self.element_factory.create_operation(
            id_short=action_name,
            input_vars=input_variables if input_variables else None,
            output_vars=output_variables if output_variables else None,
            inoutput_vars=inoutput_variables if inoutput_variables else None,
            semantic_id=semantic_id,
            qualifiers=qualifiers if qualifiers else None,
            description=f"Operation to invoke {description} action"
        )

    def _create_operation_from_config(self, skill_name: str, skill_data: Dict,
                                      system_id: str) -> model.Operation:
        """
        Create operation from explicit skill configuration (fallback method).

        Args:
            skill_name: Name of the skill
            skill_data: Skill configuration
            system_id: System identifier

        Returns:
            Operation element
        """
        input_variables = []
        output_variables = []

        if 'input_variable' in skill_data and skill_data['input_variable']:
            for var_name, var_type in skill_data['input_variable'].items():
                input_variables.append(
                    self._create_operation_variable(var_name, var_type)
                )

        if 'output_variable' in skill_data and skill_data['output_variable']:
            for var_name, var_type in skill_data['output_variable'].items():
                output_variables.append(
                    self._create_operation_variable(var_name, var_type)
                )

        # Build qualifiers for delegation
        qualifiers = []
        if self.delegation_base_url:
            qualifiers.extend([
                model.Qualifier(
                    type_="invocationDelegation",
                    value_type=model.datatypes.String,
                    value=f"{self.delegation_base_url}/operations/{system_id}/{skill_name}",
                    kind=model.QualifierKind.CONCEPT_QUALIFIER
                ),
                model.Qualifier(
                    type_="Synchronous",
                    value_type=model.datatypes.Boolean,
                    value="true",
                    kind=model.QualifierKind.CONCEPT_QUALIFIER
                )
            ])

        return model.Operation(
            id_short=skill_name,
            input_variable=input_variables if input_variables else (),
            output_variable=output_variables if output_variables else (),
            description=model.MultiLanguageTextType(
                {"en": skill_data.get('description', f'Operation for {skill_name}')}),
            qualifier=qualifiers if qualifiers else ()
        )

    def _create_operation_variable(self, var_name: str, var_type: str,
                                   description: str = "") -> model.SubmodelElement:
        """
        Create an operation variable (input/output parameter) as a Property.

        Args:
            var_name: Name of the variable
            var_type: Type of the variable (JSON schema type)
            description: Optional description

        Returns:
            Property element for use in Operation
        """
        aas_type = self.schema_handler.get_aas_type(var_type)

        # Experimental path: use ReferenceElement as Operation variable.
        # Keys that identify AAS elements must use string identifiers.
        # prop = model.ReferenceElement(
        #     id_short=var_name,
        #     value=model.ModelReference(
        #         (model.Key(
        #             type_=model.KeyTypes.SUBMODEL,
        #             value=f"{self.base_url}/submodels/instances/Test/Skills"
        #         ),
        #             model.Key(
        #             type_=model.KeyTypes.SUBMODEL_ELEMENT_COLLECTION,
        #             value="Skill"
        #         ),
        #             model.Key(
        #             type_=model.KeyTypes.SUBMODEL_ELEMENT_COLLECTION,
        #             value="SkillDescription"
        #         ),
        #             model.Key(
        #             type_=model.KeyTypes.SUBMODEL_ELEMENT_LIST,
        #             value="Parameters"
        #         ),
        #             model.Key(
        #             type_=model.KeyTypes.PROPERTY,
        #             value="1"
        #         ),),
        #         model.Property
        #     ),
        #     description=model.MultiLanguageTextType(
        #         {"en": f"Reference to the skill parameter '{var_name}'"})
        # )

        prop = model.Property(
            id_short=var_name,
            value_type=aas_type,
            display_name=model.MultiLanguageNameType({"en": var_name}),
            description=model.MultiLanguageTextType(
                {"en": description}) if description else None
        )
        return prop

    def _create_operation_qualifiers(self, action_config: Dict, system_id: str,
                                     action_name: str) -> List[model.Qualifier]:
        """
        Create qualifiers for an operation.

        Args:
            action_config: Action configuration
            system_id: System identifier
            action_name: Name of the action

        Returns:
            List of qualifiers
        """
        qualifiers = []

        # Determine operation type from config structure
        # One-way: no output schema AND no response in forms
        forms = action_config.get('forms', {})
        has_output = 'output' in action_config
        has_response = 'response' in forms
        is_one_way = not has_output and not has_response
        is_synchronous = str(action_config.get(
            'synchronous', 'true')).lower() == 'true'

        # Add invocationDelegation qualifier for BaSyx Operation Delegation
        # Operation type (oneWay, synchronous) is read from topics.json by the delegation service
        if self.delegation_base_url:
            delegation_url = f"{self.delegation_base_url}/operations/{system_id}/{action_name}"
            qualifiers.append(
                model.Qualifier(
                    type_="invocationDelegation",
                    value_type=model.datatypes.String,
                    value=delegation_url
                )
            )

        # Add operation type qualifier
        if is_one_way:
            # OneWay operations: no response expected, synchronous flag is not applicable
            qualifiers.append(
                model.Qualifier(
                    type_="OneWay",
                    value_type=model.datatypes.Boolean,
                    value=True
                )
            )
        else:
            # Two-way operations: add synchronous flag (default: true)
            qualifiers.append(
                model.Qualifier(
                    type_="Synchronous",
                    value_type=model.datatypes.Boolean,
                    value=is_synchronous
                )
            )

        return qualifiers

    def _is_async_operation(self, action_config: Dict) -> bool:
        """
        Determine if an operation is asynchronous based on action configuration.

        Args:
            action_config: Action configuration dictionary

        Returns:
            True if the operation is asynchronous (synchronous=false), False otherwise
        """
        # Check synchronous flag (default is true = synchronous)
        # If synchronous is false, the operation is asynchronous
        return str(action_config.get('synchronous', 'true')).lower() == 'false'

    def _create_state_machine_property(self) -> model.Property:
        """
        Create an StateMachine property for asynchronous operations.

        This property is updated by the Operation Delegation Service with
        intermediate states (IDLE, RUNNING, SUCCESS, FAILURE) during execution.
        Clients can poll this property to monitor operation progress.

        Returns:
            Property element for operation state
        """
        return model.Property(
            id_short="StateMachine",
            value_type=model.datatypes.String,
            value="IDLE",
            description=model.MultiLanguageTextType({
                "en": "Current state of the asynchronous operation. "
                      "Values: IDLE, RUNNING, SUCCESS, FAILURE. "
                      "Poll this property to monitor operation progress."
            })
        )

    def _create_interface_reference(self, interface_name: str, system_id: str) -> model.ReferenceElement:
        """
        Create a reference to an action interface.

        Args:
            interface_name: Name of the interface
            system_id: System identifier

        Returns:
            ReferenceElement pointing to the interface
        """
        return model.ReferenceElement(
            id_short="InterfaceReference",
            value=model.ModelReference(
                (model.Key(
                    type_=model.KeyTypes.SUBMODEL,
                    value=f"{self.base_url}/submodels/instances/{system_id}/AssetInterfacesDescription"
                ),
                    model.Key(
                    type_=model.KeyTypes.SUBMODEL_ELEMENT_COLLECTION,
                    value="InterfaceMQTT"
                ),
                    model.Key(
                    type_=model.KeyTypes.SUBMODEL_ELEMENT_COLLECTION,
                    value="InteractionMetadata"
                ),
                    model.Key(
                    type_=model.KeyTypes.SUBMODEL_ELEMENT_COLLECTION,
                    value="actions"
                ),
                    model.Key(
                    type_=model.KeyTypes.SUBMODEL_ELEMENT_COLLECTION,
                    value=interface_name
                ),),
                model.SubmodelElementCollection
            ),
            description=model.MultiLanguageTextType(
                {"en": f"Reference to {interface_name} action interface"})
        )

    # ══════════════════════════════════════════════════════════════════════
    #  PDDL Skill Description builders
    # ══════════════════════════════════════════════════════════════════════

    def _build_skill_description(self, skill_desc_config: Dict, system_id: str) -> model.SubmodelElementCollection:
        """
        Build SkillDescription SMC from the skill_desription YAML config.

        Produces the AAS structure::

            SMC SkillDescription
            ├─SMC Parameters
            ├─SMC ComparisonValues
            ├─SMC Duration
            ├── SMC ArithmaticTerm (optional)
            ├─SMC Conditions (optional) Obligatory once one child exists
            ├── SMC PreConditions (optional) Obligatory once one child exists
            │   └── SMC And/Or/Not/Imply (logic term, ordered)
            │       ├── SMC (display_name="Operational", idShort=$index)
            │       │   ├── SML ComparisonValues
            │       │   │   └── ReferenceElement ModelReference → Skills/$SkillName/ComparisonValues/1
            │       │   ├── SML Parameter
            │       │   │   └── ReferenceElement ModelReference → Skills/$SkillName/Parameters/1
            │       │   ├── Property EvaluationFormula (semanticID: "http://.../EvaluationFormula", supplementalSemanticIds: "https://.../euclideanDistance")
            │       │   │   └── Value: String → "Parameters[0] == ComparisonValues[0]"
            │       └── SMC (display_name="Occupied", idShort=$index)
            │       │   ├── SML Parameter
            │       │   │   └── ReferenceElement ModelReference → Skills/$SkillName/Parameters/2
            │       │   │   └── ReferenceElement ModelReference → Skills/$SkillName/Parameters/3
            │       │   ├── Property EvaluationFormula (semanticID: "http://.../EvaluationFormula", supplementalSemanticIds: "https://.../firstIn")
            │       │   │   └── Value: String → "Parameters[2].at(0) == Parameters[3]"
            ├── SMC InvariantConditions  (optional) Obligatory once one child exists
            ├── SMC PostConditions (optional) Obligatory once one child exists
            └─SMC Effects (optional) Obligatory once one child exists
            ├── SMC PreEffects (optional) Obligatory once one child exists
            ├── SMC ContinuousEffects (optional) Obligatory once one child exists
            ├── SMC PostEffects (optional) Obligatory once one child exists
                └── SMC Predicate (display_name="On", idShort=$index)
                    ├── SMC Parameter (display_name="ProductUuid", idShort=$index)
                    └── SMC Parameter (display_name="Transport", idShort=$index)
        """
        elements = []

        conditions_config = skill_desc_config.get('conditions')
        if conditions_config:
            elements.extend(self._build_conditions_section(conditions_config, system_id))

        effects_config = skill_desc_config.get('effects')
        if effects_config:
            elements.append(self._build_logic_section('Effects', effects_config, system_id))

        return model.SubmodelElementCollection(
            id_short='SkillDescription',
            value=elements,
            description=model.MultiLanguageTextType(
                {"en": "PDDL-annotated skill description with Conditions and effects supporting PDDL3.1"})
        )

    # Valid condition group names
    CONDITION_GROUPS = ['PreConditions', 'InvariantConditions', 'PostConditions']

    def _build_conditions_section(self, conditions_config: Dict,
                                  system_id: str) -> List[model.SubmodelElementCollection]:
        """
        Build PreConditions / InvariantConditions / PostConditions SMCs.

        Each group is a SubmodelElementCollection whose children are the
        logic terms (And, Or, Not, …) that belong to that condition category.
        Groups that are absent or empty in the YAML are omitted from the output.

        Returns a list of group SMCs to be added directly to the parent.
        """
        elements = []

        for group_name in self.CONDITION_GROUPS:
            group_terms = conditions_config.get(group_name)
            if not group_terms:
                continue
            group_elements = []
            items = self._normalize_terms(group_terms)
            for term_type, term_config in items:
                sml = self._build_term(term_type, term_config, system_id)
                if sml.id_short is None:
                    sml.id_short = (
                        sml.display_name.get("en", term_type)
                        if sml.display_name else term_type
                    )
                group_elements.append(sml)

            elements.append(model.SubmodelElementCollection(
                id_short=group_name,
                value=group_elements
            ))

        return elements

    def _build_logic_section(self, section_name: str,
                             section_config: Dict, system_id: str) -> model.SubmodelElementCollection:
        """
        Build a Conditions or Effects section SMC.

        The section contains one or more logic terms (and/or/not/imply) as top-level keys.
        """
        elements = []
        semantic_id = self._make_semantic_id(section_config.get('semantic_id'))
        terms_config = section_config.get('terms')
        if terms_config:
            # terms can be a list (new format) or dict (legacy)
            items = self._normalize_terms(terms_config)
            for term_type, term in items:
                sml = self._build_term(term_type, term, system_id)
                # Top-level terms live inside an SMC (Conditions/Effects),
                # so they need an id_short (AASd-117).  Nested terms inside
                # an SML are built with id_short=None (AASd-120).
                if sml.id_short is None:
                    sml.id_short = sml.display_name.get("en", term_type) if sml.display_name else term_type
                elements.append(sml)

        return model.SubmodelElementCollection(
            id_short=section_name,
            value=elements,
            semantic_id=semantic_id
        )

    def _normalize_terms(self, terms_config) -> list:
        """
        Normalize terms from either list format or dict format into
        a list of (term_type, term_config) tuples.

        List format (new):  [{term: {...}}, {predicate: {...}}]
        Dict format (legacy): {term: {...}, predicate: {...}}
        """
        items = []
        if isinstance(terms_config, list):
            for entry in terms_config:
                if isinstance(entry, dict):
                    for term_type, term_data in entry.items():
                        items.append((term_type, term_data))
        elif isinstance(terms_config, dict):
            for term_type, term_data in terms_config.items():
                items.append((term_type, term_data))
        return items

    def _build_term(self, term_type, term_config: Dict, system_id: str) -> model.SubmodelElementList:
        """
        Build a logic/arithmetic term as SML (And, Or, Not, Imply).

        Uses SubmodelElementList to preserve ordering of predicates,
        which is important for Imply and other order-dependent connectives.
        """
        
        elements = []
        qualifiers = []
        semantic_id_str = term_config.get('semantic_id')
        semantic_id = self._make_semantic_id(semantic_id_str)
        term_name = semantic_id_str.rsplit('/', 1)[-1] if semantic_id_str else term_type

        if term_type == "predicate":
            return self._build_predicate(term_name, term_config, system_id)

        # Process child terms
        terms = term_config.get('terms', [])
        if terms:
            items = self._normalize_terms(terms)
            for child_type, child_config in items:
                elements.append(self._build_term(child_type, child_config, system_id))

        return model.SubmodelElementList(
            id_short=None,
            value=elements,
            supplemental_semantic_id=[semantic_id] if semantic_id else [],
            semantic_id=self._make_semantic_id("https://smartproductionlab.aau.dk/PDDL/Term"),
            display_name=model.MultiLanguageNameType({"en": term_name.capitalize()}),
            type_value_list_element=model.SubmodelElementList,
            semantic_id_list_element=self._make_semantic_id("https://smartproductionlab.aau.dk/PDDL/Term"),
            qualifier=qualifiers
        )

    def _build_predicate(self, pred_name, pred_config: Dict, system_id: str) -> model.SubmodelElementList:
        """
        Build a predicate as an SML containing parameter SMCs.

        Supports two comparison levels:

        1. **Parameter-level** — a ``comparison`` block nested inside a
           parameter.  Creates a ``Comparison`` SMC as a child of the
           Parameter SMC.  The comparison operator is encoded as
           ``supplemental_semantic_id`` on the Comparison SMC.
        2. **Predicate-level** — an ``operator`` on the predicate itself.
           Encoded as an extra entry in the predicate SML's
           ``supplemental_semantic_id``.

        YAML format::

            # Per-parameter comparison
            predicate:
                semantic_id: ".../Operational"
                parameters:
                  - name: "PackMLState"
                    reference:
                        model:
                          - SM: Variables
                          - SMC: PackMLState
                          - Property: State
                    comparison:
                        operator: ".../Equal"
                        value: "Execute"

            # Predicate-level operator (multi-parameter)
            predicate:
                semantic_id: ".../Occupied"
                operator: ".../FirstIn"
                parameters:
                  - name: "Queue"
                    reference: {model: ...}
                  - name: "Product"
                    reference: {external: ".../Uuid"}

            # Constant parameter (no reference, value only)
            predicate:
                semantic_id: ".../InVicinity"
                operator: ".../EuclideanDistance"
                parameters:
                  - name: "Pos1"
                    reference: {model: ...}
                  - name: "Pos2"
                    reference: {model: ...}
                  - name: "Threshold"
                    value: "0.5"

        Produces::

            SML (dn="Operational", supp=[.../Predicates/Operational])
            ├── SMC (dn="PackMLState", semantic_id=.../Parameter)
            │   ├── ReferenceElement ModelReference → Variables/State
            │   └── SMC Comparison (supp=.../Equal)
            │       └── Property Value = "Execute"
            └── SMC (dn="ProductUuid", semantic_id=.../Parameter)
                └── ReferenceElement ExternalReference → .../Uuid
        """
        elements = []

        # Build parameter SMCs
        params = pred_config.get('parameters', [])
        if isinstance(params, list):
            for param in params:
                if isinstance(param, dict):
                    elements.append(self._build_parameter(param, system_id))
        elif isinstance(params, dict):
            elements.append(self._build_parameter(params, system_id))

        # supplemental_semantic_id: predicate semantic_id + optional operator
        supp_ids = []
        pred_sid = self._make_semantic_id(pred_config.get('semantic_id'))
        if pred_sid:
            supp_ids.append(pred_sid)

        # Predicate-level operator (multi-parameter evaluation)
        operator = pred_config.get('operator')
        if operator:
            supp_ids.append(self._make_semantic_id(operator))

        desc = pred_config.get('description')
        
        
        return model.SubmodelElementList(
            id_short=None,
            value=elements,
            display_name=model.MultiLanguageNameType({"en": pred_name.capitalize()}),
            description=model.MultiLanguageTextType({"en": desc}) if desc else None,
            semantic_id=self._make_semantic_id("https://smartproductionlab.aau.dk/PDDL/Term"),
            supplemental_semantic_id=supp_ids if supp_ids else [],
            type_value_list_element=model.SubmodelElementCollection,
        )

    def _build_parameter(self, param_config: Dict, system_id: str = '') -> model.SubmodelElementCollection:
        """
        Build a Parameter SMC.

        A parameter provides its value from one of three sources:

        - ``reference.model`` → AAS model reference (read from AAS at runtime)
        - ``reference.external`` → External reference (supplied by planner)
        - ``value`` → Inline constant (evaluation-only, not a PDDL argument)

        Optionally, a ``comparison`` block adds a ``Comparison`` SMC child
        for per-parameter expected-value evaluation.

        YAML format::

            # PDDL argument with per-parameter comparison
            - name: "PackMLState"
              reference:
                  model:
                    - SM: Variables
                    - SMC: PackMLState
                    - Property: State
              comparison:
                  operator: ".../Equal"
                  value: "Execute"

            # PDDL argument (no comparison)
            - name: "ProductUuid"
              reference:
                  external: ".../Uuid"

            # Constant (evaluation-only, not in PDDL signature)
            - name: "Threshold"
              value: "0.5"

            # Comparison referencing another AAS property
            - name: "Position"
              reference:
                  model: [SM: Variables, SMC: Position, Property: Current]
              comparison:
                  operator: ".../Equal"
                  reference:
                      model: [SM: Parameters, SMC: Position, Property: Home]
        """
        elements = []
        qualifiers = []
        param_name = param_config.get('name', '')

        # Source 1: reference (model or external) → ReferenceElement
        reference_config = param_config.get('reference')
        if reference_config:
            elements.append(self._build_reference(reference_config, system_id))

        # Source 2: inline value → Property (constant parameter)
        value = param_config.get('value')
        if value is not None and not reference_config:
            elements.append(model.Property(
                id_short='Value',
                value_type=model.datatypes.String,
                value=str(value)
            ))

        # Optional per-parameter comparison → Comparison SMC
        comparison_config = param_config.get('comparison')
        if comparison_config:
            elements.append(self._build_comparison(comparison_config, system_id))
        model.concept.ConceptDescription()
        # Optional PDDL type as qualifier
        pddl_type = param_config.get('type')
        if pddl_type:
            qualifiers.append(model.Qualifier(
                type_="PDDLType",
                value_type=model.datatypes.String,
                value=pddl_type,
                kind=model.QualifierKind.CONCEPT_QUALIFIER
            ))

        # id_short=None because Parameter SMCs live inside a
        # SubmodelElementList (AASd-120: SML items must not have id_short)
        return model.SubmodelElementCollection(
            id_short=None,
            display_name=model.MultiLanguageNameType({"en": param_name}),
            value=elements,
            semantic_id=self._make_semantic_id("https://smartproductionlab.aau.dk/PDDL/Parameter"),
            qualifier=qualifiers if qualifiers else ()
        )

    def _build_comparison(self, comparison_config: Dict, system_id: str = '') -> model.SubmodelElementCollection:
        """
        Build a Comparison SMC for per-parameter expected-value evaluation.

        The comparison operator is encoded as ``supplemental_semantic_id``
        on the Comparison SMC.  The expected value comes from one of:

        - ``value`` → inline literal → ``Property Value``
        - ``reference.model`` → AAS path → ``ReferenceElement ModelReference``
        - ``reference.external`` → URI → ``ReferenceElement ExternalReference``

        YAML format::

            comparison:
                operator: ".../Equal"
                value: "Execute"           # inline literal

            comparison:
                operator: ".../Equal"
                reference:
                    model:                 # AAS path to expected value
                      - SM: Parameters
                      - SMC: Position
                      - Property: Home

        Produces::

            SMC Comparison (supp=.../Comparison/Equal)
            └── Property Value = "Execute"

        Lives inside a Parameter SMC (AASd-117 requires id_short
        since parent is SMC, not SML).
        """
        elements = []
        supp_ids = []

        # Operator → supplemental_semantic_id
        operator = comparison_config.get('operator')
        if operator:
            supp_ids.append(self._make_semantic_id(operator))

        # Expected value source
        value = comparison_config.get('value')
        if value is not None:
            elements.append(model.Property(
                id_short='Value',
                value_type=model.datatypes.String,
                value=str(value)
            ))

        reference_config = comparison_config.get('reference')
        if reference_config:
            elements.append(self._build_reference(reference_config, system_id))

        return model.SubmodelElementCollection(
            id_short='Comparison',
            value=elements,
            supplemental_semantic_id=supp_ids if supp_ids else [],
            semantic_id=self._make_semantic_id("https://smartproductionlab.aau.dk/PDDL/Comparison"),
        )

    def _build_reference(self, ref_config: Dict, system_id: str = '') -> model.SubmodelElement:
        """
        Build a ReferenceElement from a parameter's reference config.

        Supports two forms:

        1. ``{model: [...]}`` → ``ReferenceElement`` with ``ModelReference``
           (value read from AAS state at runtime)
        2. ``{external: <URI>}`` → ``ReferenceElement`` with ``ExternalReference``
           (value supplied by planner/executor at runtime)

        Args:
            ref_config: Dict with either 'model' or 'external' key.
            system_id: System identifier for qualifying submodel paths.

        Returns:
            ReferenceElement (ModelReference or ExternalReference)
        """
        if 'model' in ref_config:
            _KEY_TYPE_MAP = {
                "AAS": model.KeyTypes.ASSET_ADMINISTRATION_SHELL,
                "SM":  model.KeyTypes.SUBMODEL,
                "SMC": model.KeyTypes.SUBMODEL_ELEMENT_COLLECTION,
                "SML": model.KeyTypes.SUBMODEL_ELEMENT_LIST,
                "SME": model.KeyTypes.SUBMODEL_ELEMENT,
                "Property": model.KeyTypes.PROPERTY,
            }
            keys = []
            model_config = ref_config.get('model')
            for entry in model_config:
                for element_name, element in entry.items():
                    key_type = _KEY_TYPE_MAP.get(element_name)
                    if key_type:
                        if element_name == "SM" and system_id:
                            element = f"{self.base_url}/submodels/instances/{system_id}/{element}"
                        keys.append(model.Key(type_=key_type, value=element))
            return model.ReferenceElement(
                id_short='ModelReference',
                value=model.ModelReference(
                    tuple(keys),
                    model.Property
                ),
                description=model.MultiLanguageTextType(
                    {"en": "Model reference to an AAS Property"})
            )

        if 'external' in ref_config:
            return model.ReferenceElement(
                id_short='ExternalReference',
                value=model.ExternalReference(
                    (model.Key(
                        type_=model.KeyTypes.GLOBAL_REFERENCE,
                        value=ref_config.get('external', '')
                    ),)
                ),
                description=model.MultiLanguageTextType(
                    {"en": "External/ontology reference (value supplied at runtime)"})
            )

        raise ValueError(
            f"Invalid reference config: must contain 'model' or 'external' key. Got: {ref_config}")

    def _make_semantic_id(self, semantic_id_str: Optional[str]) -> Optional[model.ExternalReference]:
        """Create an ExternalReference semantic ID from a URI string, or None."""
        if not semantic_id_str:
            return None
        return model.ExternalReference(
            (model.Key(type_=model.KeyTypes.GLOBAL_REFERENCE, value=semantic_id_str),)
        )
