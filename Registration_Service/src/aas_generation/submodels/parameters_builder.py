"""Parameters Submodel Builder for AAS generation."""

from typing import Dict
from basyx.aas import model


class ParametersSubmodelBuilder:
    """
    Builder class for creating Parameters submodel.
    
    The Parameters submodel is typically empty, serving as a placeholder
    for future parameter definitions.
    """
    
    def __init__(self, base_url: str, semantic_factory):
        """
        Initialize the Parameters submodel builder.
        
        Args:
            base_url: Base URL for AAS identifiers
            semantic_factory: SemanticIdFactory instance for semantic IDs
        """
        self.base_url = base_url
        self.semantic_factory = semantic_factory
    
    def build(self, system_id: str, config: Dict) -> model.Submodel:
        """
        Create the Parameters submodel.
        
        Args:
            system_id: Unique identifier for the system
            config: Configuration dictionary (currently unused)
            
        Returns:
            Parameters submodel instance (typically empty)
        """
        submodel = model.Submodel(
            id_=f"{self.base_url}/submodels/instances/{system_id}/Parameters",
            id_short="Parameters",
            kind=model.ModellingKind.INSTANCE,
            semantic_id=self.semantic_factory.PARAMETERS_SUBMODEL,
            administration=model.AdministrativeInformation(version="1", revision="0"),
            submodel_element=[]
        )
        
        return submodel
