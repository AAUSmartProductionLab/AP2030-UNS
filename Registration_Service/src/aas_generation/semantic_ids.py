"""
Semantic ID Factory

Centralizes creation of semantic IDs and references for AAS elements.
"""

from basyx.aas import model
from typing import List, Optional


class SemanticIdCatalog:
    """Canonical semantic ID URI constants used across Registration Service."""

    SMART_PRODUCTION_LAB_BASE = "https://smartproductionlab.aau.dk"
    PLANNING_WIKI_BASE = "https://planning.wiki/ref"
    CSSX_BASE = "http://www.w3id.org/aau-ra/cssx#"

    # IDTA and common submodel semantic IDs
    IDTA_ASSET_INTERFACES = "https://admin-shell.io/idta/AssetInterfacesDescription/1/0"
    IDTA_ASSET_INTERFACES_SUBMODEL = "https://admin-shell.io/idta/AssetInterfacesDescription/1/0/Submodel"
    IDTA_ASSET_INTERFACES_INTERFACE = "https://admin-shell.io/idta/AssetInterfacesDescription/1/0/Interface"
    IDTA_ASSET_INTERFACES_INTERACTION = "https://admin-shell.io/idta/AssetInterfacesDescription/1/0/InteractionMetadata"
    IDTA_ASSET_INTERFACES_REFERENCE = "https://admin-shell.io/idta/AssetInterfacesDescription/1/0/InterfaceReference"
    IDTA_VARIABLES_SUBMODEL = "https://admin-shell.io/idta/Variables/1/0/Submodel"
    IDTA_PARAMETERS_SUBMODEL = "https://admin-shell.io/idta/Parameters/1/0/Submodel"
    IDTA_NAMEPLATE = "https://admin-shell.io/zvei/nameplate/1/0/Nameplate"
    IDTA_TECHNICAL_DATA = "https://admin-shell.io/ZVEI/TechnicalData/Submodel/1/2"
    IDTA_HIERARCHICAL_STRUCTURES_1_0 = "https://admin-shell.io/idta/HierarchicalStructures/1/0/Submodel"
    IDTA_HIERARCHICAL_STRUCTURES_1_1 = "https://admin-shell.io/idta/HierarchicalStructures/1/1/Submodel"
    IDTA_HIERARCHICAL_ARCHETYPE = "https://admin-shell.io/idta/HierarchicalStructures/ArcheType/1/0"
    IDTA_HIERARCHICAL_ENTRY_NODE = "https://admin-shell.io/idta/HierarchicalStructures/EntryNode/1/0"
    IDTA_HIERARCHICAL_NODE = "https://admin-shell.io/idta/HierarchicalStructures/Node/1/0"
    IDTA_HIERARCHICAL_SAME_AS = "https://admin-shell.io/idta/HierarchicalStructures/SameAs/1/0"
    IDTA_HIERARCHICAL_RELATIONSHIP = "https://admin-shell.io/idta/HierarchicalStructures/Relationship/1/0"
    IDTA_CARBON_FOOTPRINT = "https://admin-shell.io/idta/CarbonFootprint/0/9/ProductCarbonFootprint"

    # Legacy custom submodel semantic IDs retained for compatibility
    LEGACY_VARIABLES_SUBMODEL = "http://smartproductionlab.aau.dk/submodels/Variables/1/0"
    LEGACY_PARAMETERS_SUBMODEL = "http://smartproductionlab.aau.dk/submodels/Parameters/1/0"
    LEGACY_SKILLS_SUBMODEL = "http://smartproductionlab.aau.dk/submodels/Skills/1/0"
    LEGACY_CAPABILITIES_SUBMODEL = "http://smartproductionlab.aau.dk/submodels/OfferedCapabilityDescription/1/0"

    # Process-related submodel semantic IDs
    PROCESS_INFORMATION_SUBMODEL = f"{CSSX_BASE}ProcessInformationSubmodel"
    REQUIRED_CAPABILITIES_SUBMODEL = f"{CSSX_BASE}RequiredCapabilitiesSubmodel"
    POLICY_SUBMODEL = f"{CSSX_BASE}PolicySubmodel"
    BILL_OF_PROCESSES_SUBMODEL = f"{CSSX_BASE}BillOfProcessesSubmodel"
    PROCESS_STEP_SUBMODEL = f"{CSSX_BASE}ProcessStepSubmodel"
    PROCESS_LIST_SUBMODEL = f"{CSSX_BASE}ProcessListSubmodel"
    REQUIREMENTS_SUBMODEL = f"{CSSX_BASE}RequirementsSubmodel"

    # W3C Thing Description semantic IDs
    WOT_TD = "https://www.w3.org/2019/wot/td"
    WOT_ACTION = "https://www.w3.org/2019/wot/td#ActionAffordance"
    WOT_PROPERTY = "https://www.w3.org/2019/wot/td#PropertyAffordance"
    WOT_INTERACTION = "https://www.w3.org/2019/wot/td#InteractionAffordance"

    # MQTT and capability model semantic IDs
    MQTT_PROTOCOL = "http://www.w3.org/2011/mqtt"
    SKILLS_SUBMODEL = "https://smartfactory.de/aas/submodel/Skills#1/0"
    CAPABILITIES_SUBMODEL = "https://smartfactory.de/aas/submodel/Capabilities#1/0"
    CAPABILITY_SET = "https://smartfactory.de/aas/submodel/OfferedCapabilityDescription/CapabilitySet#1/0"
    CAPABILITY_CONTAINER = "https://smartfactory.de/aas/submodel/OfferedCapabilityDescription/CapabilitySet/CapabilityContainer#1/0"
    CAPABILITY = "https://wiki.eclipse.org/BaSyx_/_Documentation_/_Submodels_/_Capability#Capability"
    CAPABILITY_RELATIONS = "https://wiki.eclipse.org/BaSyx_/_Documentation_/_Submodels_/_Capability#CapabilityRelationships"
    CAPABILITY_REALIZED_BY = "https://wiki.eclipse.org/BaSyx_/_Documentation_/_Submodels_/_Capability#CapabilityRealizedBy"

    # Specific asset IDs
    SERIAL_NUMBER = "https://admin-shell.io/aas/3/0/SpecificAssetId/SerialNumber"
    LOCATION = "https://admin-shell.io/aas/3/0/SpecificAssetId/Location"

    # AI Planning submodel and sections (proper ontology classes)
    AI_PLANNING_SUBMODEL = f"{CSSX_BASE}AIPlanningSubmodel"
    AI_PLANNING_DOMAIN = f"{CSSX_BASE}PlanningDomain"
    AI_PLANNING_PROBLEM = f"{CSSX_BASE}PlanningProblem"
    AI_PLANNING_DOMAIN_ACTIONS = f"{CSSX_BASE}ActionCollection"
    AI_PLANNING_DOMAIN_ACTION = f"{CSSX_BASE}ActionDefinition"
    AI_PLANNING_DOMAIN_FLUENTS = f"{CSSX_BASE}FluentCollection"
    AI_PLANNING_PROBLEM_METRIC = f"{CSSX_BASE}ProblemMetric"

    # PDDL core terms/elements (proper ontology classes)
    PDDL_TERM = f"{CSSX_BASE}PDDLTerm"
    PDDL_PARAMETERS = f"{CSSX_BASE}PDDLParameterList"
    PDDL_PARAMETER = f"{CSSX_BASE}PDDLParameter"
    PDDL_OBJECTS = f"{CSSX_BASE}PDDLObjectList"
    PDDL_OBJECT = f"{CSSX_BASE}PDDLObject"
    PDDL_DURATION = f"{CSSX_BASE}PDDLDuration"
    PDDL_CONDITIONS = f"{CSSX_BASE}PDDLConditionList"
    PDDL_EFFECTS = f"{CSSX_BASE}PDDLEffectList"
    PDDL_METRIC_IS_VIOLATED = f"{CSSX_BASE}PDDLMetricViolation"

    PDDL_LOGIC_BASE = f"{CSSX_BASE}PDDLLogicTerm"
    PDDL_ARITH_BASE = f"{CSSX_BASE}PDDLArithmeticTerm"
    PDDL_NONDET_BASE = f"{CSSX_BASE}PDDLNondeterministicTerm"
    PDDL_TEMPORAL_BASE = f"{CSSX_BASE}PDDLTemporalTerm"

    LOGIC_SEMANTIC_IDS = {
        "and": f"{CSSX_BASE}And",
        "or": f"{CSSX_BASE}Or",
        "not": f"{CSSX_BASE}Not",
        "imply": f"{CSSX_BASE}Imply",
        "forall": f"{CSSX_BASE}Forall",
        "exists": f"{CSSX_BASE}Exists",
        "when": f"{CSSX_BASE}When",
    }

    ARITHMETIC_SEMANTIC_IDS = {
        "=": f"{CSSX_BASE}Equal",
        "eq": f"{CSSX_BASE}Equal",
        "<": f"{CSSX_BASE}LessThan",
        "<=": f"{CSSX_BASE}LessOrEqual",
        ">": f"{CSSX_BASE}GreaterThan",
        ">=": f"{CSSX_BASE}GreaterOrEqual",
        "+": f"{CSSX_BASE}Add",
        "-": f"{CSSX_BASE}Subtract",
        "*": f"{CSSX_BASE}Multiply",
        "/": f"{CSSX_BASE}Divide",
        "assign": f"{CSSX_BASE}Assign",
        "increase": f"{CSSX_BASE}Increase",
        "decrease": f"{CSSX_BASE}Decrease",
        "scale-up": f"{CSSX_BASE}ScaleUp",
        "scale-down": f"{CSSX_BASE}ScaleDown",
    }

    NONDET_SEMANTIC_IDS = {
        "oneof": f"{CSSX_BASE}OneOf",
    }

    TEMPORAL_SEMANTIC_IDS = {
        "always": f"{CSSX_BASE}Always",
        "sometime": f"{CSSX_BASE}Sometime",
        "within": f"{CSSX_BASE}Within",
        "at-most-once": f"{CSSX_BASE}AtMostOnce",
        "sometime-after": f"{CSSX_BASE}SometimeAfter",
        "sometime-before": f"{CSSX_BASE}SometimeBefore",
        "always-within": f"{CSSX_BASE}AlwaysWithin",
        "hold-during": f"{CSSX_BASE}HoldDuring",
        "hold-after": f"{CSSX_BASE}HoldAfter",
        "preference": f"{CSSX_BASE}Preference",
    }

    # Mapping from AI Planning section names to ontology class IRIs
    _AI_PLANNING_SECTION_MAP = {
        "Domain": f"{CSSX_BASE}PlanningDomain",
        "Problem": f"{CSSX_BASE}PlanningProblem",
        "Constraints": f"{CSSX_BASE}PlanningConstraints",
    }

    _AI_PLANNING_DOMAIN_SECTION_MAP = {
        "Actions": f"{CSSX_BASE}ActionCollection",
        "Action": f"{CSSX_BASE}ActionDefinition",
        "Fluents": f"{CSSX_BASE}FluentCollection",
    }

    _AI_PLANNING_PROBLEM_SECTION_MAP = {
        "Init": f"{CSSX_BASE}ProblemInit",
        "Goal": f"{CSSX_BASE}ProblemGoal",
        "Metric": f"{CSSX_BASE}ProblemMetric",
        "Objects": f"{CSSX_BASE}PDDLObjectList",
    }

    @classmethod
    def ai_planning_section(cls, section_name: str) -> str:
        return cls._AI_PLANNING_SECTION_MAP.get(
            section_name, f"{cls.CSSX_BASE}AIPlanningSubmodel"
        )

    @classmethod
    def ai_planning_domain_section(cls, section_name: str) -> str:
        return cls._AI_PLANNING_DOMAIN_SECTION_MAP.get(
            section_name, f"{cls.CSSX_BASE}PlanningDomain"
        )

    @classmethod
    def ai_planning_problem_section(cls, section_name: str) -> str:
        return cls._AI_PLANNING_PROBLEM_SECTION_MAP.get(
            section_name, f"{cls.CSSX_BASE}PlanningProblem"
        )

    @classmethod
    def recognized_submodel_templates(cls) -> set:
        """Known semantic IDs recognized by validation as standard templates."""
        return {
            cls.IDTA_ASSET_INTERFACES,
            cls.IDTA_NAMEPLATE,
            cls.IDTA_TECHNICAL_DATA,
            cls.IDTA_HIERARCHICAL_STRUCTURES_1_0,
            cls.IDTA_HIERARCHICAL_STRUCTURES_1_1,
            cls.IDTA_CARBON_FOOTPRINT,
            cls.LEGACY_VARIABLES_SUBMODEL,
            cls.LEGACY_PARAMETERS_SUBMODEL,
            cls.LEGACY_SKILLS_SUBMODEL,
            cls.LEGACY_CAPABILITIES_SUBMODEL,
        }

    @classmethod
    def wot_semantic_ids(cls) -> set:
        """Known W3C Thing Description semantic IDs used in submodels."""
        return {
            cls.WOT_ACTION,
            cls.WOT_PROPERTY,
            cls.WOT_INTERACTION,
        }


class SemanticIdFactory:
    """Factory for creating semantic IDs and references."""
    
    # IDTA Semantic IDs (URL strings)
    _ASSET_INTERFACES = SemanticIdCatalog.IDTA_ASSET_INTERFACES
    _ASSET_INTERFACES_SUBMODEL = SemanticIdCatalog.IDTA_ASSET_INTERFACES_SUBMODEL
    _ASSET_INTERFACES_INTERFACE = SemanticIdCatalog.IDTA_ASSET_INTERFACES_INTERFACE
    _ASSET_INTERFACES_INTERACTION = SemanticIdCatalog.IDTA_ASSET_INTERFACES_INTERACTION
    _ASSET_INTERFACES_REFERENCE = SemanticIdCatalog.IDTA_ASSET_INTERFACES_REFERENCE
    
    _VARIABLES_SUBMODEL = SemanticIdCatalog.IDTA_VARIABLES_SUBMODEL
    _PARAMETERS_SUBMODEL = SemanticIdCatalog.IDTA_PARAMETERS_SUBMODEL
    
    _HIERARCHICAL_STRUCTURES = SemanticIdCatalog.IDTA_HIERARCHICAL_STRUCTURES_1_1
    _HIERARCHICAL_ARCHETYPE = SemanticIdCatalog.IDTA_HIERARCHICAL_ARCHETYPE
    _HIERARCHICAL_ENTRY_NODE = SemanticIdCatalog.IDTA_HIERARCHICAL_ENTRY_NODE
    _HIERARCHICAL_NODE = SemanticIdCatalog.IDTA_HIERARCHICAL_NODE
    _HIERARCHICAL_SAME_AS = SemanticIdCatalog.IDTA_HIERARCHICAL_SAME_AS
    _HIERARCHICAL_RELATIONSHIP = SemanticIdCatalog.IDTA_HIERARCHICAL_RELATIONSHIP
    
    # W3C Thing Description
    _WOT_TD = SemanticIdCatalog.WOT_TD
    _WOT_ACTION = SemanticIdCatalog.WOT_ACTION
    _WOT_PROPERTY = SemanticIdCatalog.WOT_PROPERTY
    _WOT_INTERACTION = SemanticIdCatalog.WOT_INTERACTION
    
    # MQTT Protocol
    _MQTT_PROTOCOL = SemanticIdCatalog.MQTT_PROTOCOL
    
    # Custom Submodels
    _SKILLS_SUBMODEL = SemanticIdCatalog.SKILLS_SUBMODEL
    _CAPABILITIES_SUBMODEL = SemanticIdCatalog.CAPABILITIES_SUBMODEL
    _CAPABILITY_SET = SemanticIdCatalog.CAPABILITY_SET
    _CAPABILITY_CONTAINER = SemanticIdCatalog.CAPABILITY_CONTAINER
    _CAPABILITY = SemanticIdCatalog.CAPABILITY
    _CAPABILITY_RELATIONS = SemanticIdCatalog.CAPABILITY_RELATIONS
    _CAPABILITY_REALIZED_BY = SemanticIdCatalog.CAPABILITY_REALIZED_BY
    
    # Specific Asset IDs
    _SERIAL_NUMBER = SemanticIdCatalog.SERIAL_NUMBER
    _LOCATION = SemanticIdCatalog.LOCATION
    
    # Properties that return ExternalReference objects
    @property
    def ASSET_INTERFACES_DESCRIPTION(self) -> model.ExternalReference:
        return self.create_external_reference(self._ASSET_INTERFACES_SUBMODEL)
    
    @property
    def INTERFACE(self) -> model.ExternalReference:
        return self.create_external_reference(self._ASSET_INTERFACES_INTERFACE)
    
    @property
    def INTERACTION_METADATA(self) -> model.ExternalReference:
        return self.create_external_reference(self._ASSET_INTERFACES_INTERACTION)
    
    @property
    def INTERFACE_REFERENCE(self) -> model.ExternalReference:
        return self.create_external_reference(self._ASSET_INTERFACES_REFERENCE)
    
    @property
    def VARIABLES_SUBMODEL(self) -> model.ExternalReference:
        return self.create_external_reference(self._VARIABLES_SUBMODEL)
    
    @property
    def PARAMETERS_SUBMODEL(self) -> model.ExternalReference:
        return self.create_external_reference(self._PARAMETERS_SUBMODEL)
    
    @property
    def HIERARCHICAL_STRUCTURES(self) -> model.ExternalReference:
        return self.create_external_reference(self._HIERARCHICAL_STRUCTURES)
    
    @property
    def ENTRY_NODE(self) -> model.ExternalReference:
        return self.create_external_reference(self._HIERARCHICAL_ENTRY_NODE)
    
    @property
    def HIERARCHICAL_ARCHETYPE(self) -> model.ExternalReference:
        return self.create_external_reference(self._HIERARCHICAL_ARCHETYPE)
    
    @property
    def HIERARCHICAL_NODE(self) -> model.ExternalReference:
        return self.create_external_reference(self._HIERARCHICAL_NODE)
    
    @property
    def HIERARCHICAL_SAME_AS(self) -> model.ExternalReference:
        return self.create_external_reference(self._HIERARCHICAL_SAME_AS)
    
    @property
    def HIERARCHICAL_RELATIONSHIP(self) -> model.ExternalReference:
        return self.create_external_reference(self._HIERARCHICAL_RELATIONSHIP)
    
    @property
    def WOT_THING_DESCRIPTION(self) -> model.ExternalReference:
        return self.create_external_reference(self._WOT_TD)
    
    @property
    def WOT_ACTION_AFFORDANCE(self) -> model.ExternalReference:
        return self.create_external_reference(self._WOT_ACTION)
    
    @property
    def WOT_PROPERTY_AFFORDANCE(self) -> model.ExternalReference:
        return self.create_external_reference(self._WOT_PROPERTY)
    
    @property
    def WOT_INTERACTION_AFFORDANCE(self) -> model.ExternalReference:
        return self.create_external_reference(self._WOT_INTERACTION)
    
    @property
    def MQTT_PROTOCOL(self) -> model.ExternalReference:
        return self.create_external_reference(self._MQTT_PROTOCOL)
    
    @property
    def SKILLS_SUBMODEL(self) -> model.ExternalReference:
        return self.create_external_reference(self._SKILLS_SUBMODEL)
    
    @property
    def CAPABILITIES_SUBMODEL(self) -> model.ExternalReference:
        return self.create_external_reference(self._CAPABILITIES_SUBMODEL)
    
    @property
    def CAPABILITY_SET(self) -> model.ExternalReference:
        return self.create_external_reference(self._CAPABILITY_SET)
    
    @property
    def CAPABILITY_CONTAINER(self) -> model.ExternalReference:
        return self.create_external_reference(self._CAPABILITY_CONTAINER)
    
    @property
    def CAPABILITY(self) -> model.ExternalReference:
        return self.create_external_reference(self._CAPABILITY)
    
    @property
    def CAPABILITY_RELATIONS(self) -> model.ExternalReference:
        return self.create_external_reference(self._CAPABILITY_RELATIONS)
    
    @property
    def CAPABILITY_REALIZED_BY(self) -> model.ExternalReference:
        return self.create_external_reference(self._CAPABILITY_REALIZED_BY)

    @property
    def SERIAL_NUMBER(self) -> model.ExternalReference:
        return self.create_external_reference(self._SERIAL_NUMBER)

    @property
    def LOCATION(self) -> model.ExternalReference:
        return self.create_external_reference(self._LOCATION)
    
    @staticmethod
    def create_external_reference(semantic_id: str) -> model.ExternalReference:
        """
        Create an external reference for a semantic ID.
        
        Args:
            semantic_id: The semantic ID URL
            
        Returns:
            ExternalReference object
        """
        return model.ExternalReference(
            (model.Key(
                type_=model.KeyTypes.GLOBAL_REFERENCE,
                value=semantic_id
            ),)
        )
    
    @staticmethod
    def create_model_reference(
        reference_chain: List[tuple],
        referred_type: type
    ) -> model.ModelReference:
        """
        Create a model reference with a chain of keys.
        
        Args:
            reference_chain: List of (key_type, value) tuples
            referred_type: The type being referred to
            
        Returns:
            ModelReference object
        """
        keys = tuple(
            model.Key(type_=key_type, value=value)
            for key_type, value in reference_chain
        )
        return model.ModelReference(keys, referred_type)
    
    @staticmethod
    def create_submodel_reference(submodel_id: str) -> model.ModelReference:
        """
        Create a reference to a submodel.
        
        Args:
            submodel_id: Submodel identifier
            
        Returns:
            ModelReference to the submodel
        """
        return model.ModelReference(
            (model.Key(
                type_=model.KeyTypes.SUBMODEL,
                value=submodel_id
            ),),
            model.Submodel
        )
    
    @staticmethod
    def create_skill_semantic_id(
        skill_name: str,
        base_url: str = SemanticIdCatalog.SMART_PRODUCTION_LAB_BASE,
    ) -> model.ExternalReference:
        """
        Create a semantic ID for a skill.
        
        Args:
            skill_name: Name of the skill
            base_url: Base URL for the semantic ID
            
        Returns:
            ExternalReference for the skill
        """
        return SemanticIdFactory.create_external_reference(
            f"{base_url}/skills/{skill_name}"
        )
