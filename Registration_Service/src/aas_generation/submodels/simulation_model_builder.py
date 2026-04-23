"""Simulation Model Submodel Builder for AAS generation."""

from typing import Dict, Optional
from basyx.aas import model


class SimulationModelBuilder:
    """
    Builder class for creating SimulationModel submodel.

    The SimulationModel submodel stores the file path to the simulation model
    of an asset. This allows Python scripts and simulation environments to
    dynamically request and load the appropriate simulation model for an asset.

    Config format:
        SimulationModel:
            ModelPath: "path/to/simulation/model.py"
            Description: "Optional description of the simulation model"
    """

    # Semantic ID for the SimulationModel submodel
    SEMANTIC_ID = "https://smartproductionlab.aau.dk/submodels/SimulationModel/1/0"

    def __init__(self, base_url: str, semantic_factory, element_factory):
        """
        Initialize the SimulationModel submodel builder.

        Args:
            base_url: Base URL for AAS identifiers
            semantic_factory: SemanticIdFactory instance for semantic IDs
            element_factory: AASElementFactory instance for element creation
        """
        self.base_url = base_url
        self.semantic_factory = semantic_factory
        self.element_factory = element_factory

    def build(self, system_id: str, config: Dict) -> Optional[model.Submodel]:
        """
        Create the SimulationModel submodel.

        Args:
            system_id: Unique identifier for the system
            config: Configuration dictionary containing SimulationModel section

        Returns:
            SimulationModel submodel instance, or None if not configured
        """
        simulation_config = config.get('SimulationModel', {})
        if not simulation_config:
            return None

        elements = []

        # ModelPath property - stores the path to the simulation model file
        model_path = simulation_config.get('ModelPath')
        if model_path:
            elements.append(model.Property(
                id_short="ModelPath",
                value_type=model.datatypes.String,
                value=str(model_path),
                description=model.MultiLanguageNameType({
                    "en": "URL to the simulation model"
                })
            ))
        else:
            # ModelPath is required
            return None
        
        # ModelPath property - stores the path to the simulation model file
        model_path_raw_file = simulation_config.get('ModelPathRawFile')
        if model_path_raw_file:
            elements.append(model.Property(
                id_short="ModelPathRawFile",
                value_type=model.datatypes.String,
                value=str(model_path_raw_file),
                description=model.MultiLanguageNameType({
                    "en": "URL to the raw simulation model file"
                })
            ))

        # Optional Description property
        description = simulation_config.get('Description')
        if description:
            elements.append(model.Property(
                id_short="Description",
                value_type=model.datatypes.String,
                value=str(description),
                description=model.MultiLanguageNameType({
                    "en": "Description of the simulation model"
                })
            ))

        # Optional ModelType property (e.g., "SimulinkModel", "PythonModule", "FMU")
        model_type = simulation_config.get('ModelType')
        if model_type:
            elements.append(model.Property(
                id_short="ModelType",
                value_type=model.datatypes.String,
                value=str(model_type),
                description=model.MultiLanguageNameType({
                    "en": "Simulation model type (Simulink, Python, FMU)"
                })
            ))

        # Optional Version property
        version = simulation_config.get('Version')
        if version:
            elements.append(model.Property(
                id_short="Version",
                value_type=model.datatypes.String,
                value=str(version),
                description=model.MultiLanguageNameType({
                    "en": "Version of the simulation model"
                })
            ))

        # Create and return the submodel
        return model.Submodel(
            id_=f"{self.base_url}/submodels/instances/{system_id}/SimulationModel",
            id_short="SimulationModel",
            kind=model.ModellingKind.INSTANCE,
            semantic_id=model.ExternalReference(
                key=(model.Key(type_=model.KeyTypes.GLOBAL_REFERENCE, value=self.SEMANTIC_ID),)
            ),
            administration=model.AdministrativeInformation(version="1", revision="0"),
            submodel_element=elements
        )
