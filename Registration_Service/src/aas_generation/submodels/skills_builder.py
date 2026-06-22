"""Skills Submodel Builder for AAS generation."""

from typing import Dict, List, Optional
from basyx.aas import model
from .. semantic_ids import SemanticIdFactory

semantic_factory = SemanticIdFactory()

class SkillsSubmodelBuilder:
    """
    Builder class for creating Skills submodel.

    The Skills submodel contains Operations derived from action interfaces,
    each wrapped in a SubmodelElementCollection with interface references.
    """

    def __init__(self, base_url: str, delegation_base_url: Optional[str],schema_handler):
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
        skills_config = config.get('Skills', []) or []
        if not isinstance(skills_config, list):
            raise ValueError("Invalid Skills config: expected a list")
        skill_elements = []

        # Get action interfaces from AssetInterfacesDescription
        interface_config = config.get('AssetInterfacesDescription', {}) or {}
        mqtt_config = interface_config.get('InterfaceMQTT', {}) or {}
        interaction_metadata = mqtt_config.get('InteractionMetadata', {}) or {}
        actions = interaction_metadata.get('actions', []) or []
        action_map = {
            action.get('key'): action
            for action in actions
            if isinstance(action, dict) and action.get('key')
        }


        # If explicit Skills are configured, use them
        if skills_config:
            for skill_config in skills_config:
                if not isinstance(skill_config, dict):
                    raise ValueError("Invalid Skills entry: expected object")

                skill = SkillBuilder(skill_config, action_map, system_id, self.base_url, self.delegation_base_url, self.schema_handler)
                if skill.SMC:
                    skill_elements.append(skill.SMC)

        # Create submodel
        submodel = model.Submodel(
            id_=f"{self.base_url}/submodels/instances/{system_id}/Skills",
            id_short="Skills",
            kind=model.ModellingKind.INSTANCE,
            semantic_id=semantic_factory.SKILLS_SUBMODEL,
            administration=model.AdministrativeInformation(
                version="1", revision="0"),
            submodel_element=skill_elements
        )

        return submodel

class SkillBuilder:
    def __init__(self, config: Dict, action_map, system_id, base_url, delegation_url, schema_handler):
        self.action_map = action_map

        self.config: Dict=config
        self.parameters_config: List[Dict] = []

        self.name=self.config.get('key')
        self.system_id=system_id
        self.base_url=base_url
        self.delegation_url=delegation_url
        self.schema_handler=schema_handler
        self.SMC=None
        self._exec_params: list[Dict] = []  # reset per skill

        self._create()

    def _create(self):
        """
        Create a skill collection with operation and interface reference.

        Args:
            skill_config: Configuration for the skill
            action_config: List of action config dicts
            system_id: System identifier

        Returns:
            SubmodelElementCollection containing the skill operation
        """
        # Get the interface name for this skill
        skill_name = self.config.get('key')
        if not isinstance(skill_name, str) or not skill_name:
            raise ValueError("Invalid Skills entry: missing or invalid 'key'")

        interface_name = self.config.get('InterfaceReference')
        if interface_name is None:
            interface_name = skill_name
        if not isinstance(interface_name, str) or not interface_name:
            raise ValueError(
                f"Invalid Skills entry '{skill_name}': InterfaceReference must be a string"
            )

        elements = []
        is_async = False

        # Create the Operation from the linked action interface
        action_config = self.action_map.get(interface_name)
        if action_config:
            operation = self._create_operation(
                skill_name, action_config, self.system_id
            )
            elements.append(operation)

            # Determine if this is an asynchronous operation
            is_async = self._is_async_operation(action_config)

            # Create reference to the action interface
            interface_reference = self._create_interface_reference(
                interface_name, self.system_id)
            elements.append(interface_reference)

        # Build ExecutionModel if configured
        execution_config = self.config.get('ExecutionModel')
        if execution_config:
            execution_model = self._build_execution_model(execution_config)
            if execution_model:
                elements.append(execution_model)
  

        if not elements:
            return None

        # For asynchronous operations, add an StateMachine property
        # This property can be polled by clients for intermediate state updates
        if is_async:
            state_property = self._create_state_machine_property()
            elements.append(state_property)

        # Wrap operation and reference in a SubmodelElementCollection
        self.SMC = model.SubmodelElementCollection(
            id_short=skill_name,
            value=tuple(elements) if elements else (),
            description=model.MultiLanguageTextType({
                "en": self.config.get('description', f'Skill: {skill_name}')
            })
        )
    
    def _create_operation(self, action_name: str, action_config: Dict,
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

        # Use semantic_id from skill config if provided, otherwise construct one
        config_semantic_id = self.config.get('semantic_id')
        if config_semantic_id:
            semantic_id = SemanticIdFactory.create_external_reference(config_semantic_id)
        else:
            semantic_id = SemanticIdFactory.create_skill_semantic_id(action_name)

        # Build the qualifiers for the operation
        qualifiers = self._create_operation_qualifiers(
            action_config, system_id, action_name)

        # Use element factory to create the operation
        return model.Operation(
            id_short=action_name,
            input_variable=tuple(input_variables) if input_variables else (),
            output_variable=tuple(output_variables) if output_variables else (),
            in_output_variable=tuple(inoutput_variables) if inoutput_variables else (),
            semantic_id=semantic_id,
            qualifier=tuple(qualifiers) if qualifiers else (),
            description=model.MultiLanguageTextType({
                "en": f"Operation to invoke {description} action"
            })
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
        if self.delegation_url:
            delegation_url = f"{self.delegation_url}/operations/{system_id}/{action_name}"
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

    # ── ExecutionModel builder (replaces separate AI-Planning submodel) ──────

    # Logic / arithmetic / FOND operator semantic IDs
    _CSSX = 'http://www.w3id.org/aau-ra/cssx#'
    _LOGIC_OPS = {
        'and':    f'{_CSSX}And',
        'or':     f'{_CSSX}Or',
        'not':    f'{_CSSX}Not',
        'oneOf':  f'{_CSSX}OneOf',
        'when':   f'{_CSSX}When',
    }

    def _build_execution_model(self, exec_cfg: Dict) -> model.SubmodelElementCollection | None:
        """Build the ExecutionModel SMC for this skill."""
        elements: list[model.SubmodelElement] = []

        # Parameters (SubmodelElementList — preserves ordering)
        params = exec_cfg.get('Parameters', []) or []
        self._exec_params = params
        if params:
            param_elements = [self._build_parameter_ref(i, p) for i, p in enumerate(params)]
            elements.append(model.SubmodelElementList(
                id_short="Parameters",
                type_value_list_element=model.ReferenceElement,
                semantic_id_list_element=SemanticIdFactory.create_external_reference(
                    f'{self._CSSX}ExecutionModelParameter'),
                value=tuple(p for p in param_elements if p is not None),
            ))

        # Conditions and Effects with timing groups
        timing_groups = {
            'Conditions': ['PreConditions', 'InvariantConditions', 'PostConditions'],
            'Effects': ['StartEffects', 'ContinuousEffects', 'EndEffects'],
        }
        for section_key, group_names in timing_groups.items():
            section_cfg = exec_cfg.get(section_key, {}) or {}
            group_elements = []
            for group_name in group_names:
                group_cfg = section_cfg.get(group_name, []) or []
                terms = [self._build_term_tree(t, i) for i, t in enumerate(group_cfg)]
                group_elements.append(model.SubmodelElementCollection(
                    id_short=group_name,
                    value=tuple(t for t in terms if t is not None),
                ))
            if group_elements:
                elements.append(model.SubmodelElementCollection(
                    id_short=section_key,
                    value=tuple(group_elements),
                ))

        if not elements:
            return None

        return model.SubmodelElementCollection(
            id_short="ExecutionModel",
            value=tuple(elements),
            description=model.MultiLanguageTextType({
                "en": "Symbolic execution model: parameters, conditions, and effects"
            }),
        )

    # ── Submodel ID helpers ─────────────────────────────────────────────────────

    @property
    def _skills_submodel_id(self) -> str:
        return f"{self.base_url}/submodels/instances/{self.system_id}/Skills"

    def _param_path_keys(self, param_idx: int) -> list[model.Key]:
        """ModelReference keys pointing to a parameter by index inside the
        SubmodelElementList."""
        return [
            model.Key(model.KeyTypes.SUBMODEL, self._skills_submodel_id),
            model.Key(model.KeyTypes.SUBMODEL_ELEMENT_COLLECTION, self.name),
            model.Key(model.KeyTypes.SUBMODEL_ELEMENT_COLLECTION, "ExecutionModel"),
            model.Key(model.KeyTypes.SUBMODEL_ELEMENT_LIST, "Parameters"),
            model.Key(model.KeyTypes.SUBMODEL_ELEMENT_COLLECTION, str(param_idx)),
        ]

    # ── Parameter builder ────────────────────────────────────────────────────────

    def _build_parameter_ref(self, idx: int, param_cfg: Dict) -> model.ReferenceElement | None:
        """Build a ReferenceElement for one execution-model parameter.

        - modelRef given → ModelReference with explicit keys.
        - semanticId only (no modelRef) → ExternalReference to the ontology concept.
        """
        param_name = param_cfg.get('key') or f"param_{idx}"
        semantic_id_str = param_cfg.get('semanticId') or param_cfg.get('semantic_id')
        model_ref = param_cfg.get('modelRef')

        if model_ref:
            parts = model_ref if isinstance(model_ref, list) else [model_ref]
            has_aas = any(isinstance(p, dict) and 'AAS' in p for p in parts)
            has_path = any(
                isinstance(p, dict) and
                ('Submodel' in p or 'Element' in p or 'Property' in p)
                for p in parts)
            drop_aas = has_aas and has_path  # AASd-125: drop AAS if Submodel follows

            keys: list[model.Key] = []
            for part in parts:
                if not isinstance(part, dict):
                    continue
                if 'AAS' in part:
                    if drop_aas:
                        continue
                    v = part['AAS']
                    if v == 'self':
                        v = f"{self.base_url}/aas/{self.system_id}"
                    keys.append(model.Key(model.KeyTypes.ASSET_ADMINISTRATION_SHELL, str(v)))
                if 'Submodel' in part:
                    keys.append(model.Key(model.KeyTypes.SUBMODEL, str(part['Submodel'])))
                if 'Element' in part:
                    keys.append(model.Key(model.KeyTypes.SUBMODEL_ELEMENT_COLLECTION, str(part['Element'])))
                if 'Property' in part:
                    keys.append(model.Key(model.KeyTypes.PROPERTY, str(part['Property'])))
            if not keys:
                return None  # modelRef parsed to empty keys
            ref_value = model.ModelReference(
                tuple(keys),
                keys[-1].type,
            )
        elif semantic_id_str:
            ref_value = model.ExternalReference(
                (model.Key(model.KeyTypes.GLOBAL_REFERENCE, semantic_id_str),)
            )
        else:
            return None

        # All list elements share a common semantic_id (AASd-114).
        # Individual type info lives in the reference value (ModelRef/ExternalRef).
        semantic_id = SemanticIdFactory.create_external_reference(f'{self._CSSX}ExecutionModelParameter')

        return model.ReferenceElement(
            id_short=None,  # SubmodelElementList auto-assigns [N]
            display_name=model.MultiLanguageNameType({"en": param_name}),
            value=ref_value,
        )

    # ── Term tree builder (recursive) ────────────────────────────────────────────

    def _build_term_tree(self, term_cfg: Dict, idx: int) -> model.SubmodelElementCollection | None:
        """Recursively build a term tree (predicate / logic / FOND).

        Recognised YAML shapes:

        * Atomic predicate
            {"predicate": "cssx:Operational", "args": [...]}
            {"predicate": ..., "args": [...], "negated": true}  → wrapped in ``not``

        * Logic operators
            {"and":  [child, …]}
            {"or":   [child, …]}
            {"not":  [child]}
            {"oneOf": [{"when": "…", ...}, …]}
        """
        if not isinstance(term_cfg, dict):
            return None

        # ── operator dispatch ──
        # ``when`` is special: its value is a condition string, not child terms.
        if 'when' in term_cfg:
            when_cond = term_cfg['when']
            child_cfg = {k: v for k, v in term_cfg.items() if k != 'when'}
            return self._build_compound_term('when', [child_cfg], idx, {'when': when_cond})

        for op_key in ('and', 'or', 'not', 'oneOf'):
            if op_key in term_cfg:
                children = term_cfg[op_key]
                if not isinstance(children, list):
                    children = [children]
                return self._build_compound_term(op_key, children, idx, term_cfg)

        # ── atomic predicate ──
        predicate_uri = term_cfg.get('predicate') or term_cfg.get('semantic_id')
        if predicate_uri:
            negated = term_cfg.get('negated', False)
            if negated:
                # Strip negated to avoid infinite recursion
                clean_cfg = {k: v for k, v in term_cfg.items() if k != 'negated'}
                return self._build_compound_term('not', [clean_cfg], idx, {'negated': True})
            return self._build_atomic_term(predicate_uri, term_cfg.get('args', []), idx)

        return None

    def _build_atomic_term(
        self, predicate_uri: str, args: list, idx: int
    ) -> model.SubmodelElementCollection:
        """Build a predicate term SMC with Arg_N children."""
        short_name = predicate_uri.rsplit('#', 1)[-1] if '#' in predicate_uri else predicate_uri.rsplit('/', 1)[-1]

        elements: list[model.SubmodelElement] = []
        for i, arg in enumerate(args):
            ref = self._build_term_arg(arg, i)
            if ref is not None:
                elements.append(ref)

        return model.SubmodelElementCollection(
            id_short=f"term_{idx}",
            value=tuple(elements),
            semantic_id=SemanticIdFactory.create_external_reference(predicate_uri),
            display_name=model.MultiLanguageNameType({"en": short_name}),
        )

    def _build_compound_term(
        self, operator: str,
        children: list[Dict],
        idx: int,
        parent_cfg: Dict | None = None,
    ) -> model.SubmodelElementCollection | None:
        """Build a logic / FOND term containing child terms."""
        if not children:
            return None

        op_semantic = self._LOGIC_OPS.get(operator, f'{self._CSSX}{operator.capitalize()}')
        display = operator.capitalize()

        # ``when`` prepends the condition string
        when_condition = ''
        if operator == 'when' and isinstance(parent_cfg, dict):
            when_condition = str(parent_cfg.get('when', ''))
            display = f"{display}: {when_condition}" if when_condition else display

        elements: list[model.SubmodelElement] = []
        for i, child_cfg in enumerate(children):
            child = self._build_term_tree(child_cfg, i)
            if child is not None:
                elements.append(child)

        if not elements:
            return None

        return model.SubmodelElementCollection(
            id_short=f"term_{idx}",
            value=tuple(elements),
            semantic_id=SemanticIdFactory.create_external_reference(op_semantic),
            display_name=model.MultiLanguageNameType({"en": display}),
        )

    # ── Argument builder ─────────────────────────────────────────────────────

    def _get_param_name(self, idx: int) -> str:
        """Return the parameter key at the given index, or '?' if out of range."""
        params = getattr(self, '_exec_params', []) or []
        if 0 <= idx < len(params) and isinstance(params[idx], dict):
            return params[idx].get('key', '?')
        return '?'

    def _build_term_arg(self, arg_cfg, idx: int) -> model.ReferenceElement | None:
        """Build a ReferenceElement for a term argument.

        Args are integer indices (or legacy string names) referring to a
        parameter position in the Parameters SMC.

        idShort = ``param_N``, displayName = actual parameter key.
        """
        if isinstance(arg_cfg, int):
            param_idx = arg_cfg
        elif isinstance(arg_cfg, str):
            param_idx = int(arg_cfg)
        elif isinstance(arg_cfg, dict):
            # legacy dict format — extract numeric value
            raw = arg_cfg.get('value', arg_cfg.get('Literal', ''))
            param_idx = int(raw)
        else:
            param_idx = int(arg_cfg)

        param_name = self._get_param_name(param_idx)

        return model.ReferenceElement(
            id_short=f"param_{param_idx}",
            display_name=model.MultiLanguageNameType({"en": param_name}),
            value=model.ModelReference(
                tuple(self._param_path_keys(param_idx)),
                model.KeyTypes.SUBMODEL_ELEMENT_COLLECTION,
            ),
        )