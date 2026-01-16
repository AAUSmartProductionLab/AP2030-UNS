"""
Semantic ID Factory

Centralizes creation of semantic IDs and references for AAS elements.
"""

from basyx.aas import model
from typing import List, Optional


class SemanticIdFactory:
    """Factory for creating semantic IDs and references."""
    
    # IDTA Semantic IDs (URL strings)
    _ASSET_INTERFACES = "https://admin-shell.io/idta/AssetInterfacesDescription/1/0"
    _ASSET_INTERFACES_SUBMODEL = "https://admin-shell.io/idta/AssetInterfacesDescription/1/0/Submodel"
    _ASSET_INTERFACES_INTERFACE = "https://admin-shell.io/idta/AssetInterfacesDescription/1/0/Interface"
    _ASSET_INTERFACES_INTERACTION = "https://admin-shell.io/idta/AssetInterfacesDescription/1/0/InteractionMetadata"
    _ASSET_INTERFACES_REFERENCE = "https://admin-shell.io/idta/AssetInterfacesDescription/1/0/InterfaceReference"
    
    _VARIABLES_SUBMODEL = "https://admin-shell.io/idta/Variables/1/0/Submodel"
    _PARAMETERS_SUBMODEL = "https://admin-shell.io/idta/Parameters/1/0/Submodel"
    
    _HIERARCHICAL_STRUCTURES = "https://admin-shell.io/idta/HierarchicalStructures/1/1/Submodel"
    _HIERARCHICAL_ARCHETYPE = "https://admin-shell.io/idta/HierarchicalStructures/ArcheType/1/0"
    _HIERARCHICAL_ENTRY_NODE = "https://admin-shell.io/idta/HierarchicalStructures/EntryNode/1/0"
    _HIERARCHICAL_NODE = "https://admin-shell.io/idta/HierarchicalStructures/Node/1/0"
    _HIERARCHICAL_SAME_AS = "https://admin-shell.io/idta/HierarchicalStructures/SameAs/1/0"
    _HIERARCHICAL_RELATIONSHIP = "https://admin-shell.io/idta/HierarchicalStructures/Relationship/1/0"
    
    # W3C Thing Description
    _WOT_TD = "https://www.w3.org/2019/wot/td"
    _WOT_ACTION = "https://www.w3.org/2019/wot/td#ActionAffordance"
    _WOT_PROPERTY = "https://www.w3.org/2019/wot/td#PropertyAffordance"
    _WOT_INTERACTION = "https://www.w3.org/2019/wot/td#InteractionAffordance"
    
    # MQTT Protocol
    _MQTT_PROTOCOL = "http://www.w3.org/2011/mqtt"
    
    # Custom Submodels
    _SKILLS_SUBMODEL = "https://smartfactory.de/aas/submodel/Skills#1/0"
    _CAPABILITIES_SUBMODEL = "https://smartfactory.de/aas/submodel/Capabilities#1/0"
    _CAPABILITY_SET = "https://smartfactory.de/aas/submodel/OfferedCapabilitiyDescription/CapabilitySet#1/0"
    _CAPABILITY_CONTAINER = "https://smartfactory.de/aas/submodel/OfferedCapabilitiyDescription/CapabilitySet/CapabilityContainer#1/0"
    _CAPABILITY = "https://wiki.eclipse.org/BaSyx_/_Documentation_/_Submodels_/_Capability#Capability"
    _CAPABILITY_RELATIONS = "https://wiki.eclipse.org/BaSyx_/_Documentation_/_Submodels_/_Capability#CapabilityRelationships"
    _CAPABILITY_REALIZED_BY = "https://wiki.eclipse.org/BaSyx_/_Documentation_/_Submodels_/_Capability#CapabilityRealizedBy"
    
    # Specific Asset IDs
    _SERIAL_NUMBER = "https://admin-shell.io/aas/3/0/SpecificAssetId/SerialNumber"
    _LOCATION = "https://admin-shell.io/aas/3/0/SpecificAssetId/Location"
    
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
    def create_skill_semantic_id(skill_name: str, base_url: str = "https://smartproductionlab.aau.dk") -> model.ExternalReference:
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
