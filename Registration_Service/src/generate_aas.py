#!/usr/bin/env python3
"""
AAS Generator Script
This script generates Asset Administration Shell (AAS) descriptions programmatically
using the basyx-python-sdk from YAML configuration files.

Usage:
    python generate_aas.py --config aas_config.yaml --output output_dir/
"""

import json
import yaml
import argparse
import os
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from basyx.aas import model
from basyx.aas.adapter.json import json_serialization
from .aas_validator import AASValidator


# JSON Schema to AAS datatypes mapping
SCHEMA_TYPE_TO_AAS_TYPE = {
    'string': model.datatypes.String,
    'integer': model.datatypes.Int,
    'number': model.datatypes.Double,
    'boolean': model.datatypes.Boolean,
    'array': model.datatypes.String,  # Arrays serialized as JSON strings
    'object': model.datatypes.String,  # Objects serialized as JSON strings
}


class AASGenerator:
    """Generates AAS descriptions from configuration files."""
    
    def __init__(self, config_path: str, delegation_base_url: str = None):
        """
        Initialize the AAS Generator.
        
        Args:
            config_path: Path to the YAML configuration file
            delegation_base_url: Base URL for Operation Delegation Service
                                 (e.g., 'http://operation-delegation:8087')
        """
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        # Base URL is now derived from individual system IDs
        self.base_url = None
        self.idta_version = '1.0'
        
        # Operation Delegation Service URL for BaSyx invocationDelegation
        # This service translates AAS Operation invocations to MQTT commands
        self.delegation_base_url = delegation_base_url or os.environ.get(
            'DELEGATION_SERVICE_URL', 
            'http://192.168.0.104:8087'
        )
        
    def generate_all(self, output_dir: str, validate: bool = True):
        """
        Generate AAS file from the configuration.
        
        Args:
            output_dir: Directory to save the generated JSON file
            validate: If True, validate the generated AAS
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Config contains a single system with the system ID as the top-level key
        system_id = list(self.config.keys())[0]
        system_config = self.config[system_id]
        
        print(f"Generating AAS for {system_id}...")
        obj_store, aas_dict = self.generate_system(system_id, system_config, return_store=True)
        
        # Validate if enabled
        if validate:
            print(f"Validating {system_id}...")
            if not self.validate_generated_aas(obj_store, system_id):
                print(f"\n❌ Validation failed for {system_id}")
                return False
        
        # Save to JSON file
        output_file = output_path / f"{system_id}.json"
        with open(output_file, 'w') as f:
            json.dump(aas_dict, f, indent=2)
        
        print(f"Saved to {output_file}")
        return True
    
    def validate_generated_aas(self, obj_store: model.DictObjectStore, context: str = "") -> bool:
        """
        Validate a generated AAS object store.
        
        Args:
            obj_store: The DictObjectStore containing generated AAS objects
            context: Context string for error messages (e.g., system name)
            
        Returns:
            True if validation passed (no errors), False otherwise
        """
        validator = AASValidator()
        result = validator.validate(obj_store)
        
        if not result.is_valid():
            print(f"\n⚠️  Validation errors found for {context}:")
            print(result.summary())
            return False
        elif result.warnings:
            print(f"\n✓ Validation passed for {context} (with {len(result.warnings)} warning(s))")
            if result.warnings:
                print("Warnings:")
                for warning in result.warnings:
                    print(f"  • {warning}")
        else:
            print(f"✓ Validation passed for {context}")
        
        return True
    
    def generate_system(self, system_id: str, config: Dict, return_store: bool = False):
        """
        Generate a complete AAS for a single system.
        
        Args:
            system_id: Unique identifier for the system
            config: Configuration dictionary for this system
            return_store: If True, returns (obj_store, dict), otherwise just dict
            
        Returns:
            Dictionary representation of the AAS, or tuple of (obj_store, dict) if return_store=True
        """
        # Extract base URL from the system ID
        aas_id = config.get('id', '')
        if aas_id:
            # Extract base URL from ID (e.g., https://smartproductionlab.aau.dk/aas/...)
            parts = aas_id.rsplit('/aas/', 1)
            if len(parts) == 2:
                self.base_url = parts[0]
            else:
                self.base_url = aas_id.rsplit('/', 1)[0]
        else:
            self.base_url = 'https://smartproductionlab.aau.dk'
        
        # Create object store
        obj_store: model.DictObjectStore[model.Identifiable] = model.DictObjectStore()
        
        # Store system_id for reference creation in variable submodels
        self.current_system_id = system_id
        
        # Generate AAS
        aas = self._create_aas(system_id, config, obj_store)
        obj_store.add(aas)
        
        # Generate Submodels
        submodels = self._create_submodels(system_id, config)
        for sm in submodels:
            obj_store.add(sm)
        
        # Serialize to JSON
        json_data = json_serialization.object_store_to_json(obj_store)
        aas_dict = json.loads(json_data)
        
        if return_store:
            return obj_store, aas_dict
        return aas_dict
    
    def _create_aas(self, system_id: str, config: Dict, 
                    obj_store: model.DictObjectStore) -> model.AssetAdministrationShell:
        """Create the Asset Administration Shell."""
        
        id_short = config.get('idShort', system_id)
        aas_id = config.get('id', f"{self.base_url}/aas/{system_id}")
        global_asset_id = config.get('globalAssetId', f"{self.base_url}/assets/{system_id}")
        asset_type = config.get('assetType', '')
        serial_number = config.get('serialNumber', 'UNKNOWN')
        location = config.get('location', 'UNKNOWN')
        
        # Create asset information
        asset_information = model.AssetInformation(
            asset_kind=model.AssetKind.INSTANCE,
            global_asset_id=global_asset_id,
            asset_type=asset_type if asset_type else None
        )
        
        # Add specific asset IDs
        asset_information.specific_asset_id = {
            model.SpecificAssetId(
                name="serialNumber",
                value=serial_number,
                external_subject_id=model.ExternalReference(
                    (model.Key(
                        type_=model.KeyTypes.GLOBAL_REFERENCE,
                        value="https://admin-shell.io/aas/3/0/SpecificAssetId/SerialNumber"
                    ),)
                )
            ),
            model.SpecificAssetId(
                name="location",
                value=location,
                external_subject_id=model.ExternalReference(
                    (model.Key(
                        type_=model.KeyTypes.GLOBAL_REFERENCE,
                        value="https://admin-shell.io/aas/3/0/SpecificAssetId/Location"
                    ),)
                )
            )
        }
        
        # Create submodel references based on what's in the config
        submodel_names = []
        if 'AssetInterfacesDescription' in config:
            submodel_names.append('AssetInterfacesDescription')
        if 'Variables' in config:
            submodel_names.append('Variables')
        if 'Parameters' in config:
            submodel_names.append('Parameters')
        if 'HierarchicalStructures' in config:
            submodel_names.append('HierarchicalStructures')
        if 'Capabilities' in config and config.get('Capabilities'):
            submodel_names.append('OfferedCapabilitiyDescription')
        
        # Add Skills submodel reference if:
        # 1. Skills are explicitly defined in config, OR
        # 2. There are actions in AssetInterfacesDescription (auto-generation)
        has_explicit_skills = 'Skills' in config and config.get('Skills')
        has_actions = False
        interface_config = config.get('AssetInterfacesDescription', {}) or {}
        mqtt_config = interface_config.get('InterfaceMQTT', {}) or {}
        interaction_metadata = mqtt_config.get('InteractionMetadata', {}) or {}
        actions = interaction_metadata.get('actions', [])
        if actions:
            has_actions = True
        
        if has_explicit_skills or has_actions:
            submodel_names.append('Skills')
        
        submodel_refs = [
            model.ModelReference(
                (model.Key(
                    type_=model.KeyTypes.SUBMODEL,
                    value=f"{self.base_url}/submodels/instances/{system_id}/{sm_name}"
                ),),
                model.Submodel
            )
            for sm_name in submodel_names
        ]
        
        # Create AAS with optional derivedFrom
        aas_kwargs = {
            'id_': aas_id,
            'asset_information': asset_information,
            'id_short': id_short,
            'submodel': submodel_refs
        }
        
        # Add derivedFrom if specified in config
        derived_from = config.get('derivedFrom')
        if derived_from:
            aas_kwargs['derived_from'] = model.ModelReference(
                (model.Key(
                    type_=model.KeyTypes.ASSET_ADMINISTRATION_SHELL,
                    value=derived_from
                ),),
                model.AssetAdministrationShell
            )
        
        aas = model.AssetAdministrationShell(**aas_kwargs)
        
        return aas
    
    def _create_submodels(self, system_id: str, config: Dict) -> List[model.Submodel]:
        """Create all submodels for the system."""
        return [
            self._create_asset_interfaces_submodel(system_id, config),
            self._create_variables_submodel(system_id, config),
            self._create_parameters_submodel(system_id, config),
            self._create_hierarchical_structures_submodel(system_id, config),
            self._create_capabilities_submodel(system_id, config),
            self._create_skills_submodel(system_id, config)
        ]
    
    def _create_asset_interfaces_submodel(self, system_id: str, 
                                          config: Dict) -> model.Submodel:
        """Create the AssetInterfacesDescription submodel."""
        
        interface_config = config.get('AssetInterfacesDescription', {}) or {}
        mqtt_config = interface_config.get('InterfaceMQTT', {}) or {}
        
        # Create MQTT interface collection
        interface_elements = []
        
        # Title (lowercase to match W3C Thing Description)
        title = mqtt_config.get('Title', system_id)
        interface_elements.append(
            model.Property(
                id_short="title",
                value_type=model.datatypes.String,
                value=title
            )
        )
        
        # Add EndpointMetadata collection with MQTT topics
        endpoint_metadata = self._create_mqtt_endpoint_metadata_new(mqtt_config)
        if endpoint_metadata:
            interface_elements.append(endpoint_metadata)
        
        # Create InteractionMetadata collection with actions and properties nested
        interaction_metadata = mqtt_config.get('InteractionMetadata', {})
        interaction_elements = []
        
        actions = interaction_metadata.get('actions', [])
        if actions:
            actions_collection = self._create_actions_from_interaction_metadata(actions)
            if actions_collection:
                interaction_elements.append(actions_collection)
        
        properties = interaction_metadata.get('properties', [])
        if properties:
            properties_collection = self._create_properties_from_interaction_metadata(properties)
            if properties_collection:
                interaction_elements.append(properties_collection)
        
        # Wrap in InteractionMetadata collection if we have content
        if interaction_elements:
            interaction_metadata_collection = model.SubmodelElementCollection(
                id_short="InteractionMetadata",
                value=interaction_elements,
                semantic_id=model.ExternalReference(
                    (model.Key(
                        type_=model.KeyTypes.GLOBAL_REFERENCE,
                        value="https://admin-shell.io/idta/AssetInterfacesDescription/1/0/InteractionMetadata"
                    ),)
                ),
                supplemental_semantic_id=[
                    model.ExternalReference(
                        (model.Key(
                            type_=model.KeyTypes.GLOBAL_REFERENCE,
                            value="https://www.w3.org/2019/wot/td#InteractionAffordance"
                        ),)
                    )
                ]
            )
            interface_elements.append(interaction_metadata_collection)
        
        interface_mqtt = model.SubmodelElementCollection(
            id_short="InterfaceMQTT",
            value=interface_elements,
            semantic_id=model.ExternalReference(
                (model.Key(
                    type_=model.KeyTypes.GLOBAL_REFERENCE,
                    value="https://admin-shell.io/idta/AssetInterfacesDescription/1/0/Interface"
                ),)
            ),
            supplemental_semantic_id=[
                model.ExternalReference(
                    (model.Key(
                        type_=model.KeyTypes.GLOBAL_REFERENCE,
                        value="http://www.w3.org/2011/mqtt"
                    ),)
                ),
                model.ExternalReference(
                    (model.Key(
                        type_=model.KeyTypes.GLOBAL_REFERENCE,
                        value="https://www.w3.org/2019/wot/td"
                    ),)
                )
            ]
        )
        
        submodel = model.Submodel(
            id_=f"{self.base_url}/submodels/instances/{system_id}/AssetInterfacesDescription",
            id_short="AssetInterfacesDescription",
            kind=model.ModellingKind.INSTANCE,
            semantic_id=model.ExternalReference(
                (model.Key(
                    type_=model.KeyTypes.GLOBAL_REFERENCE,
                    value="https://admin-shell.io/idta/AssetInterfacesDescription/1/0/Submodel"
                ),)
            ),
            administration=model.AdministrativeInformation(version="1", revision="0"),
            submodel_element=[interface_mqtt]
        )
        
        return submodel
    
    def _create_mqtt_endpoint_metadata_new(self, mqtt_config: Dict) -> Optional[model.SubmodelElementCollection]:
        """Create the EndpointMetadata collection for MQTT topics from new config format."""
        
        endpoint_config = mqtt_config.get('EndpointMetadata', {})
        if not endpoint_config:
            return None
        
        endpoint_elements = []
        
        # Base endpoint
        if 'base' in endpoint_config:
            endpoint_elements.append(
                model.Property(
                    id_short="base",
                    value_type=model.datatypes.String,
                    value=endpoint_config['base']
                )
            )
        
        # Content type
        if 'contentType' in endpoint_config:
            endpoint_elements.append(
                model.Property(
                    id_short="contentType",
                    value_type=model.datatypes.String,
                    value=endpoint_config['contentType']
                )
            )
        
        if not endpoint_elements:
            return None
        
        return model.SubmodelElementCollection(
            id_short="EndpointMetadata",
            value=endpoint_elements
        )
    
    def _create_actions_from_interaction_metadata(self, actions: List[Dict]) -> Optional[model.SubmodelElementCollection]:
        """Create Actions collection from interaction metadata."""
        
        if not actions:
            return None
        
        action_elements = []
        
        for action_dict in actions:
            # Each action is a dict with one key (the action name)
            action_name = list(action_dict.keys())[0]
            action_config = action_dict[action_name]
            
            action_props = []
            
            # Key/Title
            if 'key' in action_config:
                action_props.append(
                    model.Property(
                        id_short="Key",
                        value_type=model.datatypes.String,
                        value=action_config['key']
                    )
                )
            
            if 'title' in action_config:
                action_props.append(
                    model.Property(
                        id_short="Title",
                        value_type=model.datatypes.String,
                        value=action_config['title']
                    )
                )
            
            # Synchronous flag
            if 'synchronous' in action_config:
                sync_value = str(action_config['synchronous']).lower() == 'true'
                action_props.append(
                    model.Property(
                        id_short="Synchronous",
                        value_type=model.datatypes.Boolean,
                        value=sync_value
                    )
                )
            
            # Input/Output schemas
            if 'input' in action_config:
                action_props.append(
                    model.File(
                        id_short="input",
                        content_type="application/schema+json",
                        value=action_config['input']
                    )
                )
            
            if 'output' in action_config:
                action_props.append(
                    model.File(
                        id_short="output",
                        content_type="application/schema+json",
                        value=action_config['output']
                    )
                )
            
            # Forms
            if 'forms' in action_config:
                forms_config = action_config['forms']
                form_elements = []
                
                for key, value in forms_config.items():
                    if key == 'response' and isinstance(value, dict):
                        # Response is a nested structure
                        response_elements = []
                        for resp_key, resp_value in value.items():
                            response_elements.append(
                                model.Property(
                                    id_short=resp_key,
                                    value_type=model.datatypes.String,
                                    value=str(resp_value)
                                )
                            )
                        form_elements.append(
                            model.SubmodelElementCollection(
                                id_short="response",
                                value=response_elements
                            )
                        )
                    else:
                        form_elements.append(
                            model.Property(
                                id_short=key,
                                value_type=model.datatypes.String,
                                value=str(value)
                            )
                        )
                
                if form_elements:
                    action_props.append(
                        model.SubmodelElementCollection(
                            id_short="Forms",
                            value=form_elements
                        )
                    )
            
            action_element = model.SubmodelElementCollection(
                id_short=action_name,
                value=action_props
            )
            action_elements.append(action_element)
        
        if not action_elements:
            return None
        
        return model.SubmodelElementCollection(
            id_short="actions",
            value=action_elements,
            semantic_id=model.ExternalReference(
                (model.Key(
                    type_=model.KeyTypes.GLOBAL_REFERENCE,
                    value="https://www.w3.org/2019/wot/td#ActionAffordance"
                ),)
            )
        )
    
    def _create_properties_from_interaction_metadata(self, properties: List[Dict]) -> Optional[model.SubmodelElementCollection]:
        """Create Properties collection from interaction metadata."""
        
        if not properties:
            return None
        
        property_elements = []
        
        for prop_dict in properties:
            # Each property is a dict with one key (the property name)
            prop_name = list(prop_dict.keys())[0]
            prop_config = prop_dict[prop_name]
            
            prop_elements = []
            
            # Key/Title
            if 'key' in prop_config:
                prop_elements.append(
                    model.Property(
                        id_short="Key",
                        value_type=model.datatypes.String,
                        value=prop_config['key']
                    )
                )
            
            if 'title' in prop_config:
                prop_elements.append(
                    model.Property(
                        id_short="Title",
                        value_type=model.datatypes.String,
                        value=prop_config['title']
                    )
                )
            
            # Output schema
            if 'output' in prop_config:
                prop_elements.append(
                    model.File(
                        id_short="output",
                        content_type="application/schema+json",
                        value=prop_config['output']
                    )
                )
            
            # Forms
            if 'forms' in prop_config:
                forms_config = prop_config['forms']
                form_elements = []
                
                for key, value in forms_config.items():
                    form_elements.append(
                        model.Property(
                            id_short=key,
                            value_type=model.datatypes.String,
                            value=str(value)
                        )
                    )
                
                if form_elements:
                    prop_elements.append(
                        model.SubmodelElementCollection(
                            id_short="Forms",
                            value=form_elements
                        )
                    )
            
            property_element = model.SubmodelElementCollection(
                id_short=prop_name,
                value=prop_elements
            )
            property_elements.append(property_element)
        
        if not property_elements:
            return None
        
        return model.SubmodelElementCollection(
            id_short="properties",
            value=property_elements,
            semantic_id=model.ExternalReference(
                (model.Key(
                    type_=model.KeyTypes.GLOBAL_REFERENCE,
                    value="https://www.w3.org/2019/wot/td#PropertyAffordance"
                ),)
            )
        )
    
    def _create_variables_submodel(self, system_id: str, 
                                   config: Dict) -> model.Submodel:
        """Create the Variables submodel."""
        
        variables_config = config.get('Variables', {}) or {}
        variable_elements = []
        
        # Handle dict format (no dashes): Variables: { VarName: {...}, ... }
        for var_name, var_config in variables_config.items():
            var_collection = self._create_variable_collection_new(var_name, var_config or {})
            if var_collection:
                variable_elements.append(var_collection)
        
        submodel = model.Submodel(
            id_=f"{self.base_url}/submodels/instances/{system_id}/Variables",
            id_short="Variables",
            kind=model.ModellingKind.INSTANCE,
            semantic_id=model.ExternalReference(
                (model.Key(
                    type_=model.KeyTypes.GLOBAL_REFERENCE,
                    value="https://admin-shell.io/idta/Variables/1/0/Submodel"
                ),)
            ),
            administration=model.AdministrativeInformation(version="1", revision="0"),
            submodel_element=variable_elements
        )
        
        return submodel
    
    def _create_variable_collection_new(self, var_name: str, 
                                        var_config: Dict) -> Optional[model.SubmodelElementCollection]:
        """Create a variable collection from new config format."""
        
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
            
            elements.append(
                model.Property(
                    id_short=key,
                    value_type=value_type,
                    value=value
                )
            )
        
        # Add InterfaceReference as ReferenceElement if present
        if 'InterfaceReference' in var_config:
            interface_ref_name = var_config['InterfaceReference']
            
            # Create a proper ReferenceElement pointing to the interface property
            elements.append(
                model.ReferenceElement(
                    id_short="InterfaceReference",
                    value=model.ModelReference(
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
                    semantic_id=model.ExternalReference(
                        (model.Key(
                            type_=model.KeyTypes.GLOBAL_REFERENCE,
                            value="https://admin-shell.io/idta/AssetInterfacesDescription/1/0/InterfaceReference"
                        ),)
                    )
                )
            )
        
        if not elements:
            return None
        
        collection_kwargs = {
            'id_short': var_name,
            'value': elements
        }
        
        if semantic_id:
            collection_kwargs['semantic_id'] = model.ExternalReference(
                (model.Key(
                    type_=model.KeyTypes.GLOBAL_REFERENCE,
                    value=semantic_id
                ),)
            )
        
        return model.SubmodelElementCollection(**collection_kwargs)
    
    def _create_parameters_submodel(self, system_id: str, 
                                    config: Dict) -> model.Submodel:
        """Create the Parameters submodel (typically empty)."""
        
        submodel = model.Submodel(
            id_=f"{self.base_url}/submodels/instances/{system_id}/Parameters",
            id_short="Parameters",
            kind=model.ModellingKind.INSTANCE,
            semantic_id=model.ExternalReference(
                (model.Key(
                    type_=model.KeyTypes.GLOBAL_REFERENCE,
                    value="https://admin-shell.io/idta/Parameters/1/0/Submodel"
                ),)
            ),
            administration=model.AdministrativeInformation(version="1", revision="0"),
            submodel_element=[]
        )
        
        return submodel
    
    def _create_hierarchical_structures_submodel(self, system_id: str, 
                                                 config: Dict) -> model.Submodel:
        """
        Create the HierarchicalStructures submodel.
        
        Simplified config format:
            HierarchicalStructures:
                Archetype: 'OneUp'  # or 'OneDown'
                IsPartOf:  # or HasPart for OneDown
                    - systemName:
                        globalAssetId: 'required-unique-id'
                        systemId: 'optional-config-key'  # defaults to systemName + 'AAS'
        
        Auto-derives:
            - aasId from systemName
            - submodelId from systemId (defaults to systemName + 'AAS')
        """
        
        hs_config = config.get('HierarchicalStructures', {}) or {}
        archetype = hs_config.get('Archetype', 'OneUp')
        global_asset_id = config.get('globalAssetId', f"{self.base_url}/assets/{system_id}")
        
        elements = [
            model.Property(
                id_short="ArcheType",
                value_type=model.datatypes.String,
                value=archetype,
                semantic_id=model.ExternalReference(
                    (model.Key(
                        type_=model.KeyTypes.GLOBAL_REFERENCE,
                        value="https://admin-shell.io/idta/HierarchicalStructures/ArcheType/1/0"
                    ),)
                )
            )
        ]
        
        # Create entry node with Node entities as children (per IDTA spec)
        node_entities = []
        entry_node_statements = []
        
        # Handle both IsPartOf and HasPart (now directly in config, not under 'statements')
        is_part_of = hs_config.get('IsPartOf', [])
        has_part = hs_config.get('HasPart', [])
        
        # Determine which statements to process based on archetype
        statements_to_process = []
        relationship_prefix = ""
        
        if archetype == 'OneUp':
            statements_to_process = is_part_of
            relationship_prefix = "IsPartOf"
        elif archetype == 'OneDown':
            statements_to_process = has_part
            relationship_prefix = "HasPart"
        
        # Process statements - create Node entities and RelationshipElements
        for entity_item in statements_to_process:
            # Support both string format (just system name) and dict format (with details)
            if isinstance(entity_item, str):
                # Minimal format: just the system name
                entity_name = entity_item
                entity_config = {}
            elif isinstance(entity_item, dict):
                # Dict format: {systemName: {config}} or {systemName: null}
                entity_name = list(entity_item.keys())[0]
                entity_config = entity_item[entity_name] or {}
            else:
                continue
            
            # Auto-derive missing IDs
            # Use systemId if provided, otherwise append 'AAS' to entity_name as convention
            entity_system_id = entity_config.get('systemId', f"{entity_name}AAS")
            entity_aas_id = entity_config.get('aasId', f"{self.base_url}/aas/{entity_name}")
            entity_submodel_id = entity_config.get('submodelId', f"{self.base_url}/submodels/instances/{entity_system_id}/HierarchicalStructures")
            entity_global_asset_id = entity_config.get('globalAssetId', '')
            
            # Create statements for this Node entity
            node_statements = []
            
            # Create SameAs reference element pointing to the referenced AAS EntryNode
            # (always create it now that we auto-derive the submodel ID)
            if entity_submodel_id:
                same_as = model.ReferenceElement(
                    id_short="SameAs",
                    value=model.ModelReference(
                        (
                            model.Key(
                                type_=model.KeyTypes.SUBMODEL,
                                value=entity_submodel_id
                            ),
                            model.Key(
                                type_=model.KeyTypes.ENTITY,
                                value="EntryNode"
                            )
                        ),
                        model.Entity
                    ),
                    semantic_id=model.ExternalReference(
                        (model.Key(
                            type_=model.KeyTypes.GLOBAL_REFERENCE,
                            value="https://admin-shell.io/idta/HierarchicalStructures/SameAs/1/0"
                        ),)
                    ),
                    # Add referredSemanticId to help BaSyx navigate to the EntryNode
                    supplemental_semantic_id=[
                        model.ExternalReference(
                            (model.Key(
                                type_=model.KeyTypes.GLOBAL_REFERENCE,
                                value="https://admin-shell.io/idta/HierarchicalStructures/EntryNode/1/0"
                            ),)
                        )
                    ]
                )
                node_statements.append(same_as)
            
            # Create the Node entity
            # SELF_MANAGED requires globalAssetId, CO_MANAGED doesn't
            is_self_managed = bool(entity_global_asset_id)
            node_entity = model.Entity(
                id_short=entity_name,
                entity_type=model.EntityType.SELF_MANAGED_ENTITY if is_self_managed else model.EntityType.CO_MANAGED_ENTITY,
                global_asset_id=entity_global_asset_id if entity_global_asset_id else None,
                semantic_id=model.ExternalReference(
                    (model.Key(
                        type_=model.KeyTypes.GLOBAL_REFERENCE,
                        value="https://admin-shell.io/idta/HierarchicalStructures/Node/1/0"
                    ),)
                ),
                statement=node_statements if node_statements else []
            )
            node_entities.append(node_entity)
            
            # Create relationship element
            relationship_element = model.RelationshipElement(
                id_short=f"{relationship_prefix}_{entity_name}",
                first=model.ModelReference(
                    (
                        model.Key(
                            type_=model.KeyTypes.SUBMODEL,
                            value=f"{self.base_url}/submodels/instances/{system_id}/HierarchicalStructures"
                        ),
                        model.Key(
                            type_=model.KeyTypes.ENTITY,
                            value="EntryNode"
                        )
                    ),
                    model.Entity
                ),
                second=model.ModelReference(
                    (
                        model.Key(
                            type_=model.KeyTypes.SUBMODEL,
                            value=f"{self.base_url}/submodels/instances/{system_id}/HierarchicalStructures"
                        ),
                        model.Key(
                            type_=model.KeyTypes.ENTITY,
                            value="EntryNode"
                        ),
                        model.Key(
                            type_=model.KeyTypes.ENTITY,
                            value=entity_name
                        )
                    ),
                    model.Entity
                ),
                semantic_id=model.ExternalReference(
                    (model.Key(
                        type_=model.KeyTypes.GLOBAL_REFERENCE,
                        value="https://admin-shell.io/idta/HierarchicalStructures/Relationship/1/0"
                    ),)
                )
            )
            entry_node_statements.append(relationship_element)
        
        # Add all Node entities to EntryNode statements
        entry_node_statements.extend(node_entities)
        
        entry_node = model.Entity(
            id_short="EntryNode",
            entity_type=model.EntityType.SELF_MANAGED_ENTITY,
            global_asset_id=global_asset_id,
            semantic_id=model.ExternalReference(
                (model.Key(
                    type_=model.KeyTypes.GLOBAL_REFERENCE,
                    value="https://admin-shell.io/idta/HierarchicalStructures/EntryNode/1/0"
                ),)
            ),
            statement=entry_node_statements if entry_node_statements else []
        )
        
        elements.append(entry_node)
        
        submodel = model.Submodel(
            id_=f"{self.base_url}/submodels/instances/{system_id}/HierarchicalStructures",
            id_short="HierarchicalStructures",
            kind=model.ModellingKind.INSTANCE,
            semantic_id=model.ExternalReference(
                (model.Key(
                    type_=model.KeyTypes.GLOBAL_REFERENCE,
                    value="https://admin-shell.io/idta/HierarchicalStructures/1/1/Submodel"
                ),)
            ),
            administration=model.AdministrativeInformation(version="1", revision="1"),
            submodel_element=elements
        )
        
        return submodel
    
    def _create_capabilities_submodel(self, system_id: str, config: Dict) -> model.Submodel:
        """
        Create the OfferedCapabilityDescription submodel.
        
        Args:
            system_id: Unique identifier for the system
            config: Configuration dictionary
            
        Returns:
            Capabilities submodel
        """
        capabilities = config.get('Capabilities', {}) or {}
        capability_containers = []
        
        # Handle dict format (no dashes): Capabilities: { CapName: {...}, ... }
        for cap_name, cap_config in capabilities.items():
            cap_config = cap_config or {}
            container_elements = []
            
            # Capability element (type: Capability)
            container_elements.append(
                model.Capability(
                    id_short=cap_name,
                    semantic_id=model.ExternalReference(
                        (model.Key(
                            type_=model.KeyTypes.GLOBAL_REFERENCE,
                            value="https://wiki.eclipse.org/BaSyx_/_Documentation_/_Submodels_/_Capability#Capability"
                        ),)
                    )
                )
            )
            
            # Comment
            if 'comment' in cap_config:
                container_elements.append(
                    model.MultiLanguageProperty(
                        id_short="Comment",
                        value=model.MultiLanguageTextType({"en": cap_config['comment']})
                    )
                )
            
            # CapabilityRelations (placeholder structure)
            container_elements.append(
                model.SubmodelElementCollection(
                    id_short="CapabilityRelations",
                    value=[],
                    semantic_id=model.ExternalReference(
                        (model.Key(
                            type_=model.KeyTypes.GLOBAL_REFERENCE,
                            value="https://wiki.eclipse.org/BaSyx_/_Documentation_/_Submodels_/_Capability#CapabilityRelationships"
                        ),)
                    )
                )
            )
            
            # realizedBy - relationships to skills
            realized_by = cap_config.get('realizedBy')
            if realized_by:
                # Handle both single string and list of strings
                if isinstance(realized_by, str):
                    skill_names = [realized_by]
                else:
                    skill_names = realized_by
                
                realized_by_elements = []
                for skill_name in skill_names:
                    # Create relationship element pointing to skill
                    # id_short=None for SubmodelElementList items (constraint AASd-120)
                    rel_element = model.RelationshipElement(
                        id_short=None,
                        first=model.ModelReference(
                            (model.Key(
                                type_=model.KeyTypes.SUBMODEL,
                                value=f"{self.base_url}/submodels/instances/{system_id}/OfferedCapabilitiyDescription"
                            ),
                            model.Key(
                                type_=model.KeyTypes.SUBMODEL_ELEMENT_COLLECTION,
                                value="CapabilitySet"
                            ),
                            model.Key(
                                type_=model.KeyTypes.SUBMODEL_ELEMENT_COLLECTION,
                                value=cap_config.get('id_short', cap_name + 'Container')
                            )),
                            model.SubmodelElementCollection
                        ),
                        second=model.ModelReference(
                            (model.Key(
                                type_=model.KeyTypes.SUBMODEL,
                                value=f"{self.base_url}/submodels/instances/{system_id}/Skills"
                            ),
                            model.Key(
                                type_=model.KeyTypes.SUBMODEL_ELEMENT_COLLECTION,
                                value=skill_name
                            )),
                            model.SubmodelElementCollection
                        )
                    )
                    realized_by_elements.append(rel_element)
                
                container_elements.append(
                    model.SubmodelElementList(
                        id_short="realizedBy",
                        type_value_list_element=model.RelationshipElement,
                        value=realized_by_elements,
                        semantic_id=model.ExternalReference(
                            (model.Key(
                                type_=model.KeyTypes.GLOBAL_REFERENCE,
                                value="https://wiki.eclipse.org/BaSyx_/_Documentation_/_Submodels_/_Capability#CapabilityRealizedBy"
                            ),)
                        )
                    )
                )
            
            # PropertySet
            if 'properties' in cap_config and cap_config['properties']:
                property_elements = []
                for prop in cap_config['properties']:
                    prop_container_elements = []
                    
                    # Comment (only add if description is not empty)
                    if 'description' in prop and prop['description']:
                        prop_container_elements.append(
                            model.MultiLanguageProperty(
                                id_short="Comment",
                                value=model.MultiLanguageTextType({"en": prop['description']})
                            )
                        )
                    
                    # Property value or range
                    if 'min' in prop and 'max' in prop:
                        prop_container_elements.append(
                            model.Range(
                                id_short=prop['name'],
                                value_type=model.datatypes.Double,
                                min=float(prop['min']),
                                max=float(prop['max'])
                            )
                        )
                    elif 'value' in prop:
                        prop_container_elements.append(
                            model.Property(
                                id_short=prop['name'],
                                value_type=model.datatypes.String,
                                value=prop['value']
                            )
                        )
                    
                    property_elements.append(
                        model.SubmodelElementCollection(
                            id_short=f"PropertyContainer_{prop['name']}",
                            value=prop_container_elements
                        )
                    )
                
                if property_elements:
                    container_elements.append(
                        model.SubmodelElementCollection(
                            id_short="PropertySet",
                            value=property_elements
                        )
                    )
            
            # Create capability container
            container_kwargs = {
                'id_short': cap_config.get('id_short', cap_name + 'Container'),
                'value': container_elements,
                'semantic_id': model.ExternalReference(
                    (model.Key(
                        type_=model.KeyTypes.GLOBAL_REFERENCE,
                        value="https://smartfactory.de/aas/submodel/OfferedCapabilitiyDescription/CapabilitySet/CapabilityContainer#1/0"
                    ),)
                )
            }
            
            # Only add description if it's not empty
            description = cap_config.get('description', '')
            if description:
                container_kwargs['description'] = model.MultiLanguageTextType({"en": description})
            
            capability_container = model.SubmodelElementCollection(**container_kwargs)
            capability_containers.append(capability_container)
        
        # Create CapabilitySet
        capability_set = model.SubmodelElementCollection(
            id_short="CapabilitySet",
            value=capability_containers,
            semantic_id=model.ExternalReference(
                (model.Key(
                    type_=model.KeyTypes.GLOBAL_REFERENCE,
                    value="https://smartfactory.de/aas/submodel/OfferedCapabilitiyDescription/CapabilitySet#1/0"
                ),)
            )
        )
        
        # Create submodel
        submodel = model.Submodel(
            id_=f"{self.base_url}/submodels/instances/{system_id}/OfferedCapabilitiyDescription",
            id_short="OfferedCapabilitiyDescription",
            kind=model.ModellingKind.INSTANCE,
            semantic_id=model.ExternalReference(
                (model.Key(
                    type_=model.KeyTypes.GLOBAL_REFERENCE,
                    value="https://smartfactory.de/aas/submodel/Capabilities#1/0"
                ),)
            ),
            administration=model.AdministrativeInformation(version="1", revision="0"),
            submodel_element=[capability_set]
        )
        
        return submodel
    
    def _load_schema_from_url(self, schema_url: str) -> Optional[Dict]:
        """
        Load a JSON schema from URL or local path.
        
        Args:
            schema_url: URL or local path to the schema
            
        Returns:
            Parsed schema dictionary or None if not found
        """
        # Cache for loaded schemas
        if not hasattr(self, '_schema_cache'):
            self._schema_cache = {}
        
        if schema_url in self._schema_cache:
            return self._schema_cache[schema_url]
        
        schema = None
        
        # Try to resolve the schema from local MQTTSchemas folder first
        if 'MQTTSchemas/' in schema_url or 'schemas/' in schema_url:
            # Extract filename from URL
            filename = schema_url.split('/')[-1]
            
            # Look in MQTTSchemas folder (relative to this script)
            script_dir = Path(__file__).parent.parent
            local_paths = [
                script_dir / 'MQTTSchemas' / filename,
                script_dir / 'schemas' / filename,
                Path(__file__).parent / 'schemas' / filename,
            ]
            
            for local_path in local_paths:
                if local_path.exists():
                    try:
                        with open(local_path, 'r') as f:
                            schema = json.load(f)
                        break
                    except Exception as e:
                        print(f"Warning: Could not load schema from {local_path}: {e}")
        
        # If no local file found, try to fetch from URL
        if schema is None and schema_url.startswith('http'):
            try:
                import urllib.request
                with urllib.request.urlopen(schema_url, timeout=5) as response:
                    schema = json.loads(response.read().decode())
            except Exception as e:
                print(f"Warning: Could not fetch schema from {schema_url}: {e}")
        
        if schema:
            self._schema_cache[schema_url] = schema
        
        return schema
    
    def _extract_schema_properties(self, schema: Dict, include_inherited: bool = True) -> Dict[str, Dict]:
        """
        Extract properties from a JSON schema, including from allOf references.
        
        Args:
            schema: The JSON schema dictionary
            include_inherited: Whether to include properties from referenced schemas
            
        Returns:
            Dictionary of property name -> property definition
        """
        properties = {}
        
        # Direct properties
        if 'properties' in schema:
            for prop_name, prop_def in schema['properties'].items():
                properties[prop_name] = prop_def
        
        # Handle allOf (schema composition)
        if include_inherited and 'allOf' in schema:
            for sub_schema in schema['allOf']:
                if '$ref' in sub_schema:
                    # Try to load referenced schema
                    ref_schema = self._load_schema_from_url(sub_schema['$ref'])
                    if ref_schema:
                        ref_props = self._extract_schema_properties(ref_schema, include_inherited=True)
                        properties.update(ref_props)
                elif 'properties' in sub_schema:
                    for prop_name, prop_def in sub_schema['properties'].items():
                        properties[prop_name] = prop_def
        
        return properties
    
    def _create_operation_input_property(self, var_name: str, var_type: str, 
                                   description: str = "") -> model.Property:
        """
        Create a Property for use as an Operation input/output variable.
        
        Args:
            var_name: Name of the variable
            var_type: JSON Schema type (string, integer, etc.)
            description: Optional description
            
        Returns:
            Property element for use in Operation
        """
        aas_type = SCHEMA_TYPE_TO_AAS_TYPE.get(var_type, model.datatypes.String)
        
        prop = model.Property(
            id_short=var_name,
            value_type=aas_type,
            display_name=var_name,
            description=model.MultiLanguageTextType({"en": description}) if description else None
        )
        
        return prop
    
    def _create_operation_from_action(self, action_name: str, action_config: Dict,
                                       system_id: str) -> model.Operation:
        """
        Create an AAS Operation from an action interface definition.
        
        Args:
            action_name: Name of the action
            action_config: Configuration dictionary for the action
            system_id: System identifier for references
            
        Returns:
            AAS Operation element
        """
        input_variables = []
        output_variables = []
        inoutput_variables = []
        
        # Track property names to avoid duplicates between input and output
        input_prop_names = set()
        
        # Load input schema if specified
        input_schema_url = action_config.get('input')
        if input_schema_url:
            input_schema = self._load_schema_from_url(input_schema_url)
            if input_schema:
                props = self._extract_schema_properties(input_schema)
                for prop_name, prop_def in props.items():
                    prop_type = prop_def.get('type', 'string')
                    prop_desc = prop_def.get('description', '')
                    input_variables.append(
                        self._create_operation_input_property(prop_name, prop_type, prop_desc)
                    )
                    input_prop_names.add(prop_name)
        
        # Load output schema if specified
        output_schema_url = action_config.get('output')
        if output_schema_url:
            output_schema = self._load_schema_from_url(output_schema_url)
            if output_schema:
                props = self._extract_schema_properties(output_schema)
                for prop_name, prop_def in props.items():
                    # Skip properties that already exist in input (they become in-output)
                    if prop_name in input_prop_names:
                        # Move from input to in-output
                        prop_type = prop_def.get('type', 'string')
                        prop_desc = prop_def.get('description', '')
                        inoutput_variables.append(
                            self._create_operation_input_property(prop_name, prop_type, prop_desc)
                        )
                        # Remove from input_variables
                        input_variables = [v for v in input_variables if v.id_short != prop_name]
                    else:
                        prop_type = prop_def.get('type', 'string')
                        prop_desc = prop_def.get('description', '')
                        output_variables.append(
                            self._create_operation_input_property(prop_name, prop_type, prop_desc)
                        )
        
        # Get description from action title or key
        description = action_config.get('title', action_name)
        
        # Create semantic ID from action name
        semantic_id = model.ExternalReference(
            (model.Key(
                type_=model.KeyTypes.GLOBAL_REFERENCE,
                value=f"https://smartproductionlab.aau.dk/skills/{action_name}"
            ),)
        )
        
        # Build the qualifiers for the operation to link to the interface
        qualifiers = []
        
        # Add invocationDelegation qualifier for BaSyx Operation Delegation
        # This tells BaSyx to forward operation invocations to the delegation service
        # which translates them to MQTT commands and waits for responses
        if self.delegation_base_url:
            # Build the delegation URL: /operations/<asset_id>/<skill_name>
            delegation_url = f"{self.delegation_base_url}/operations/{system_id}/{action_name}"
            qualifiers.append(
                model.Qualifier(
                    type_="invocationDelegation",
                    value_type=model.datatypes.String,
                    value=delegation_url
                )
            )
        
        # Add synchronous flag as qualifier
        if 'synchronous' in action_config:
            qualifiers.append(
                model.Qualifier(
                    type_="Synchronous",
                    value_type=model.datatypes.Boolean,
                    value=str(action_config['synchronous']).lower() == 'true'
                )
            )
        elif 'asynchronous' in action_config:
            qualifiers.append(
                model.Qualifier(
                    type_="Asynchronous",
                    value_type=model.datatypes.Boolean,
                    value=str(action_config['asynchronous']).lower() == 'true'
                )
            )
        operation = model.Operation(
            id_short="Operation",
            input_variable=input_variables if input_variables else (),
            output_variable=output_variables if output_variables else (),
            in_output_variable=inoutput_variables if inoutput_variables else (),
            description=model.MultiLanguageTextType({"en": f"Operation to invoke {description} action"}),
            semantic_id=semantic_id,
            qualifier=qualifiers if qualifiers else ()
        )
        
        return operation
    
    def _create_skills_submodel(self, system_id: str, config: Dict) -> model.Submodel:
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
        actions = interaction_metadata.get('actions', [])
        
        # Build a map of action name -> action config for easy lookup
        action_map = {}
        for action_dict in actions:
            action_name = list(action_dict.keys())[0]
            action_map[action_name] = action_dict[action_name]
        
        # If explicit Skills are configured, use them
        if skills_config:
            for skill_name, skill_data in skills_config.items():
                # Get the interface name for this skill
                interface_name = skill_data.get('interface', skill_name)
                
                # Create the Operation from the linked action interface
                if interface_name and interface_name in action_map:
                    action_config = action_map[interface_name]
                    operation = self._create_operation_from_action(
                        skill_name, action_config, system_id
                    )
                    
                    # Create reference to the action interface
                    interface_reference = model.ReferenceElement(
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
                        description=model.MultiLanguageTextType({"en": f"Reference to {interface_name} action interface"})
                    )
                    
                    # Wrap operation and reference in a SubmodelElementCollection
                    skill_collection = model.SubmodelElementCollection(
                        id_short=skill_name,
                        value=[operation, interface_reference],
                        description=model.MultiLanguageTextType({"en": skill_data.get('description', f'Skill: {skill_name}')})
                    )
                    skill_elements.append(skill_collection)
                    
                    if 'input_variable' in skill_data or 'output_variable' in skill_data:
                        # Fallback: create operation from explicit skill config
                        input_variables = []
                        output_variables = []
                        
                        if 'input_variable' in skill_data and skill_data['input_variable']:
                            for var_name, var_type in skill_data['input_variable'].items():
                                input_variables.append(
                                    self._create_operation_input_property(var_name, var_type)
                                )
                        
                        if 'output_variable' in skill_data and skill_data['output_variable']:
                            for var_name, var_type in skill_data['output_variable'].items():
                                output_variables.append(
                                    self._create_operation_input_property(var_name, var_type)
                                )
                        
                        # Build qualifiers for delegation
                        qualifiers = []
                        if self.delegation_base_url:
                            qualifiers.append(model.Qualifier(
                                type_="invocationDelegation",
                                value_type=model.datatypes.String,
                                value=f"{self.delegation_base_url}/operations/{system_id}/{skill_name}",
                                kind=model.QualifierKind.CONCEPT_QUALIFIER
                            ))
                            qualifiers.append(model.Qualifier(
                                type_="Synchronous",
                                value_type=model.datatypes.Boolean,
                                value="true",
                                kind=model.QualifierKind.CONCEPT_QUALIFIER
                            ))
                        
                        operation = model.Operation(
                            id_short=skill_name,
                            input_variable=input_variables if input_variables else (),
                            output_variable=output_variables if output_variables else (),
                            description=model.MultiLanguageTextType({"en": skill_data.get('description', f'Operation for {skill_name}')}),
                            qualifier=qualifiers if qualifiers else ()
                        )
                        
                        # Wrap operation in a SubmodelElementCollection (no interface reference for fallback)
                        skill_collection = model.SubmodelElementCollection(
                            id_short=skill_name,
                            value=[operation],
                            description=model.MultiLanguageTextType({"en": skill_data.get('description', f'Skill: {skill_name}')})
                        )
                        skill_elements.append(skill_collection)
        
        
        # Create submodel
        submodel = model.Submodel(
            id_=f"{self.base_url}/submodels/instances/{system_id}/Skills",
            id_short="Skills",
            kind=model.ModellingKind.INSTANCE,
            semantic_id=model.ExternalReference(
                (model.Key(
                    type_=model.KeyTypes.GLOBAL_REFERENCE,
                    value="https://smartfactory.de/aas/submodel/Skills#1/0"
                ),)
            ),
            administration=model.AdministrativeInformation(version="1", revision="0"),
            submodel_element=skill_elements
        )
        
        return submodel


def main():
    """Main entry point for the script."""
    
    parser = argparse.ArgumentParser(
        description='Generate AAS descriptions from configuration file'
    )
    parser.add_argument(
        '--config',
        type=str,
        default='output_test/resource_config.yaml',
        help='Path to the YAML configuration file (default: output_test/resource_config.yaml)'
    )
    parser.add_argument(
        '--output',
        type=str,
        default='Resource/',
        help='Output directory for generated JSON file (default: output_test/Resource/)'
    )
    parser.add_argument(
        '--validate',
        action='store_true',
        default=True,
        help='Validate generated AAS (default: enabled)'
    )
    parser.add_argument(
        '--no-validate',
        dest='validate',
        action='store_false',
        help='Disable AAS validation'
    )
    parser.add_argument(
        '--delegation-url',
        type=str,
        default=None,
        help='Base URL for Operation Delegation Service (e.g., http://operation-delegation:8087). '
             'If not specified, uses DELEGATION_SERVICE_URL env var or default.'
    )
    
    args = parser.parse_args()
    
    # Create generator
    generator = AASGenerator(args.config, delegation_base_url=args.delegation_url)
    
    # Generate the system
    success = generator.generate_all(args.output, validate=args.validate)
    
    print("\nGeneration complete!")
    return 0 if success else 1


if __name__ == '__main__':
    exit(main())
