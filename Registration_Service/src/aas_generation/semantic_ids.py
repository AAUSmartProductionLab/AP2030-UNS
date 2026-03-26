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
    PROCESS_INFORMATION_SUBMODEL = f"{SMART_PRODUCTION_LAB_BASE}/submodels/ProcessInformation/1/0"
    REQUIRED_CAPABILITIES_SUBMODEL = f"{SMART_PRODUCTION_LAB_BASE}/submodels/RequiredCapabilities/1/0"
    POLICY_SUBMODEL = f"{SMART_PRODUCTION_LAB_BASE}/submodels/Policy/1/0"
    BILL_OF_PROCESSES_SUBMODEL = f"{SMART_PRODUCTION_LAB_BASE}/submodels/BillOfProcesses/1/0"
    PROCESS_STEP_SUBMODEL = f"{SMART_PRODUCTION_LAB_BASE}/submodels/ProcessStep/1/0"
    PROCESS_LIST_SUBMODEL = f"{SMART_PRODUCTION_LAB_BASE}/submodels/ProcessList/1/0"
    REQUIREMENTS_SUBMODEL = f"{SMART_PRODUCTION_LAB_BASE}/submodels/Requirements/1/0"

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

    # AI Planning submodel and sections
    AI_PLANNING_SUBMODEL = f"{SMART_PRODUCTION_LAB_BASE}/submodels/AIPlanning/1/0"
    AI_PLANNING_DOMAIN = f"{SMART_PRODUCTION_LAB_BASE}/AIPlanning/Domain"
    AI_PLANNING_PROBLEM = f"{SMART_PRODUCTION_LAB_BASE}/AIPlanning/Problem"
    AI_PLANNING_DOMAIN_ACTIONS = f"{SMART_PRODUCTION_LAB_BASE}/AIPlanning/Domain/Actions"
    AI_PLANNING_DOMAIN_ACTION = f"{SMART_PRODUCTION_LAB_BASE}/AIPlanning/Domain/Action"
    AI_PLANNING_DOMAIN_FLUENTS = f"{SMART_PRODUCTION_LAB_BASE}/AIPlanning/Domain/Fluents"
    AI_PLANNING_PROBLEM_METRIC = f"{SMART_PRODUCTION_LAB_BASE}/AIPlanning/Problem/Metric"

    # PDDL core terms/elements
    PDDL_TERM = f"{SMART_PRODUCTION_LAB_BASE}/PDDL/Term"
    PDDL_PARAMETERS = f"{SMART_PRODUCTION_LAB_BASE}/PDDL/Parameters"
    PDDL_PARAMETER = f"{SMART_PRODUCTION_LAB_BASE}/PDDL/Parameter"
    PDDL_OBJECTS = f"{SMART_PRODUCTION_LAB_BASE}/PDDL/Objects"
    PDDL_OBJECT = f"{SMART_PRODUCTION_LAB_BASE}/PDDL/Object"
    PDDL_DURATION = f"{SMART_PRODUCTION_LAB_BASE}/PDDL/Duration"
    PDDL_CONDITIONS = f"{SMART_PRODUCTION_LAB_BASE}/PDDL/Conditions"
    PDDL_EFFECTS = f"{SMART_PRODUCTION_LAB_BASE}/PDDL/Effects"
    PDDL_METRIC_IS_VIOLATED = f"{SMART_PRODUCTION_LAB_BASE}/PDDL/Metric/is-violated"

    PDDL_LOGIC_BASE = f"{SMART_PRODUCTION_LAB_BASE}/PDDL/Term/Logic"
    PDDL_ARITH_BASE = f"{SMART_PRODUCTION_LAB_BASE}/PDDL/Term/Arithmetic"
    PDDL_NONDET_BASE = f"{SMART_PRODUCTION_LAB_BASE}/PDDL/Term/Nondeterministic"
    PDDL_TEMPORAL_BASE = f"{SMART_PRODUCTION_LAB_BASE}/PDDL/Term/Temporal"

    LOGIC_SEMANTIC_IDS = {
        "and": f"{PLANNING_WIKI_BASE}/pddl/domain#and",
        "or": f"{PLANNING_WIKI_BASE}/pddl/domain#or",
        "not": f"{PLANNING_WIKI_BASE}/pddl/domain#not",
        "imply": f"{PLANNING_WIKI_BASE}/pddl/domain#imply",
        "forall": f"{PLANNING_WIKI_BASE}/pddl/domain#forall",
        "exists": f"{PLANNING_WIKI_BASE}/pddl/domain#exists",
        "when": f"{PLANNING_WIKI_BASE}/pddl/domain#when",
    }

    ARITHMETIC_SEMANTIC_IDS = {
        "=": f"{PDDL_ARITH_BASE}/Equal",
        "eq": f"{PDDL_ARITH_BASE}/Equal",
        "<": f"{PDDL_ARITH_BASE}/LessThan",
        "<=": f"{PDDL_ARITH_BASE}/LessOrEqual",
        ">": f"{PDDL_ARITH_BASE}/GreaterThan",
        ">=": f"{PDDL_ARITH_BASE}/GreaterOrEqual",
        "+": f"{PLANNING_WIKI_BASE}/pddl21/domain#add",
        "-": f"{PLANNING_WIKI_BASE}/pddl21/domain#subtract",
        "*": f"{PLANNING_WIKI_BASE}/pddl21/domain#multiply",
        "/": f"{PLANNING_WIKI_BASE}/pddl21/domain#divide",
        "assign": f"{PLANNING_WIKI_BASE}/pddl21/domain#assign",
        "increase": f"{PLANNING_WIKI_BASE}/pddl21/domain#increase",
        "decrease": f"{PLANNING_WIKI_BASE}/pddl21/domain#decrease",
        "scale-up": f"{PLANNING_WIKI_BASE}/pddl21/domain#scale-up",
        "scale-down": f"{PLANNING_WIKI_BASE}/pddl21/domain#scale-down",
    }

    NONDET_SEMANTIC_IDS = {
        "oneof": f"{PDDL_NONDET_BASE}/OneOf",
    }

    TEMPORAL_SEMANTIC_IDS = {
        "always": f"{PLANNING_WIKI_BASE}/pddl3/domain#always",
        "sometime": f"{PLANNING_WIKI_BASE}/pddl3/domain#sometime",
        "within": f"{PLANNING_WIKI_BASE}/pddl3/domain#within",
        "at-most-once": f"{PLANNING_WIKI_BASE}/pddl3/domain#at-most-once",
        "sometime-after": f"{PLANNING_WIKI_BASE}/pddl3/domain#sometime-after",
        "sometime-before": f"{PLANNING_WIKI_BASE}/pddl3/domain#sometime-before",
        "always-within": f"{PLANNING_WIKI_BASE}/pddl3/domain#always-within",
        "hold-during": f"{PLANNING_WIKI_BASE}/pddl3/domain#hold-during",
        "hold-after": f"{PLANNING_WIKI_BASE}/pddl3/domain#hold-after",
        "preference": f"{PLANNING_WIKI_BASE}/pddl3/problem#preferences",
    }

    @classmethod
    def ai_planning_section(cls, section_name: str) -> str:
        return f"{cls.SMART_PRODUCTION_LAB_BASE}/AIPlanning/{section_name}"

    @classmethod
    def ai_planning_domain_section(cls, section_name: str) -> str:
        return f"{cls.SMART_PRODUCTION_LAB_BASE}/AIPlanning/Domain/{section_name}"

    @classmethod
    def ai_planning_problem_section(cls, section_name: str) -> str:
        return f"{cls.SMART_PRODUCTION_LAB_BASE}/AIPlanning/Problem/{section_name}"

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
