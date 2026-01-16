"""Variables Submodel Builder for AAS generation."""

from typing import Dict, List, Optional
from basyx.aas import model


class VariablesSubmodelBuilder:
    """
    Builder class for creating Variables submodel.
    
    The Variables submodel contains collections of variable definitions
    with their properties and optional interface references.
    """
    
    def __init__(self, base_url: str, semantic_factory, element_factory):
        """
        Initialize the Variables submodel builder.
        
        Args:
            base_url: Base URL for AAS identifiers
            semantic_factory: SemanticIdFactory instance for semantic IDs
            element_factory: AASElementFactory instance for element creation
        """
        self.base_url = base_url
        self.semantic_factory = semantic_factory
        self.element_factory = element_factory
        self.current_system_id = None
    
    def build(self, system_id: str, config: Dict) -> model.Submodel:
        """
        Create the Variables submodel.
        
        Args:
            system_id: Unique identifier for the system
            config: Configuration dictionary containing Variables section
            
        Returns:
            Variables submodel instance
        """
        self.current_system_id = system_id
        variables_config = config.get('Variables', {}) or {}
        variable_elements = []
        
        # Handle dict format (no dashes): Variables: { VarName: {...}, ... }
        for var_name, var_config in variables_config.items():
            var_collection = self._create_variable_collection(var_name, var_config or {})
            if var_collection:
                variable_elements.append(var_collection)
        
        submodel = model.Submodel(
            id_=f"{self.base_url}/submodels/instances/{system_id}/Variables",
            id_short="Variables",
            kind=model.ModellingKind.INSTANCE,
            semantic_id=self.semantic_factory.VARIABLES_SUBMODEL,
            administration=model.AdministrativeInformation(version="1", revision="0"),
            submodel_element=variable_elements
        )
        
        return submodel
    
    def _create_variable_collection(self, var_name: str, 
                                   var_config: Dict) -> Optional[model.SubmodelElementCollection]:
        """
        Create a variable collection from config format.
        
        Args:
            var_name: Name of the variable
            var_config: Configuration dictionary for the variable
            
        Returns:
            SubmodelElementCollection for the variable or None if no elements
        """
        elements = []
        
        # Add semantic ID if present
        semantic_id = var_config.get('semanticId')
        
        # Add all properties from config
        for key, value in var_config.items():
            if key in ['semanticId', 'InterfaceReference']:
                continue  # Handle these separately
            
            # Determine value type
            if isinstance(value, bool):
                value_type = model.datatypes.Boolean
            elif isinstance(value, int):
                value_type = model.datatypes.Int
            elif isinstance(value, float):
                value_type = model.datatypes.Double
            else:
                value_type = model.datatypes.String
                value = str(value)
            
            # Use element factory to create property
            elements.append(
                self.element_factory.create_property(
                    id_short=key,
                    value_type=value_type,
                    value=value
                )
            )
        
        # Add InterfaceReference as ReferenceElement if present
        if 'InterfaceReference' in var_config:
            interface_ref = self._create_interface_reference(var_config['InterfaceReference'])
            if interface_ref:
                elements.append(interface_ref)
        
        if not elements:
            return None
        
        # Build semantic ID for collection if provided
        collection_semantic_id = None
        if semantic_id:
            collection_semantic_id = self.semantic_factory.create_external_reference(semantic_id)
        
        return self.element_factory.create_collection(
            id_short=var_name,
            elements=elements,
            semantic_id=collection_semantic_id
        )
    
    def _create_interface_reference(self, interface_ref_name: str) -> Optional[model.ReferenceElement]:
        """
        Create an interface reference element.
        
        Args:
            interface_ref_name: Name of the interface property to reference
            
        Returns:
            ReferenceElement pointing to the interface property
        """
        return self.element_factory.create_reference_element(
            id_short="InterfaceReference",
            reference=model.ModelReference(
                (model.Key(
                    type_=model.KeyTypes.SUBMODEL,
                    value=f"{self.base_url}/submodels/instances/{self.current_system_id}/AssetInterfacesDescription"
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
                    value="properties"
                ),
                model.Key(
                    type_=model.KeyTypes.SUBMODEL_ELEMENT_COLLECTION,
                    value=interface_ref_name
                )),
                model.SubmodelElementCollection
            ),
            semantic_id=self.semantic_factory.INTERFACE_REFERENCE
        )
