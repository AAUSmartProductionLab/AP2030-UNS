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
from .aas_generation import AASElementFactory, SchemaHandler, SemanticIdFactory, AASBuilder
from .aas_generation.submodels import (
    AssetInterfacesBuilder,
    VariablesSubmodelBuilder,
    SkillsSubmodelBuilder,
    ParametersSubmodelBuilder,
    HierarchicalStructuresSubmodelBuilder,
    CapabilitiesSubmodelBuilder
)


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
        # Load configuration
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)

        # Extract system info from config
        self.system_id = list(self.config.keys())[0]
        self.system_config = self.config[self.system_id]

        # Set base URL from system configuration
        self.base_url = self._extract_base_url(self.system_config)

        # Operation Delegation Service URL for BaSyx invocationDelegation
        self.delegation_base_url = delegation_base_url or os.environ.get(
            'DELEGATION_SERVICE_URL',
            'http://operation-delegation:8087'
        )

        # Initialize all helper services and builders
        self._initialize_builders()

    # ==================== Initialization Methods ====================

    def _extract_base_url(self, config: Dict) -> str:
        """
        Extract base URL from system configuration.

        Args:
            config: System configuration dictionary

        Returns:
            Base URL for the system
        """
        aas_id = config.get('id', '')
        if aas_id:
            # Extract base URL from ID (e.g., https://smartproductionlab.aau.dk/aas/...)
            parts = aas_id.rsplit('/aas/', 1)
            if len(parts) == 2:
                return parts[0]
            return aas_id.rsplit('/', 1)[0]
        return 'https://smartproductionlab.aau.dk'

    def _initialize_builders(self):
        """Initialize all factory and builder instances."""
        # Core helper services
        self.schema_handler = SchemaHandler()
        self.element_factory = AASElementFactory()
        self.semantic_factory = SemanticIdFactory()

        # AAS builder
        self.aas_builder = AASBuilder(self.base_url)

        # Submodel builders
        self.asset_interfaces_builder = AssetInterfacesBuilder(
            self.base_url, self.semantic_factory, self.element_factory
        )
        self.variables_builder = VariablesSubmodelBuilder(
            self.base_url, self.semantic_factory, self.element_factory,
            self.schema_handler
        )
        self.skills_builder = SkillsSubmodelBuilder(
            self.base_url, self.delegation_base_url,
            self.semantic_factory, self.element_factory, self.schema_handler
        )
        self.parameters_builder = ParametersSubmodelBuilder(
            self.base_url, self.semantic_factory
        )
        self.hierarchical_structures_builder = HierarchicalStructuresSubmodelBuilder(
            self.base_url, self.semantic_factory, self.element_factory
        )
        self.capabilities_builder = CapabilitiesSubmodelBuilder(
            self.base_url, self.semantic_factory, self.element_factory
        )

    # ==================== Main Generation Methods ====================

    def generate_all(self, output_dir: str, validate: bool = True) -> bool:
        """
        Generate and save AAS file from the configuration.

        Args:
            output_dir: Directory to save the generated JSON file
            validate: If True, validate the generated AAS

        Returns:
            True if generation succeeded, False otherwise
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        print(f"Generating AAS for {self.system_id}...")

        # Generate AAS
        obj_store = self._build_object_store()

        # Validate if requested
        if validate and not self._validate_object_store(obj_store):
            print(f"\n❌ Validation failed for {self.system_id}")
            return False

        # Serialize and save
        aas_dict = self._serialize_to_dict(obj_store)
        output_file = output_path / f"{self.system_id}.json"

        with open(output_file, 'w') as f:
            json.dump(aas_dict, f, indent=2)

        print(f"Saved to {output_file}")
        return True

    def generate_system(self, system_id: str, config: Dict, return_store: bool = False):
        """
        Legacy compatibility method for generating AAS.

        Note: This method exists for backward compatibility with existing code.
        New code should use generate_all() instead.

        Args:
            system_id: Unique identifier for the system (ignored, uses config system_id)
            config: Configuration dictionary for this system (ignored, uses loaded config)
            return_store: If True, returns (obj_store, dict), otherwise just dict

        Returns:
            Dictionary representation of the AAS, or tuple of (obj_store, dict) if return_store=True
        """
        obj_store = self._build_object_store()
        aas_dict = self._serialize_to_dict(obj_store)

        if return_store:
            return obj_store, aas_dict
        return aas_dict

    def validate_generated_aas(self, obj_store: model.DictObjectStore, context: str = "") -> bool:
        """
        Legacy compatibility method for validation.

        Note: This method exists for backward compatibility with existing code.
        New code should use _validate_object_store() or generate_all(validate=True).

        Args:
            obj_store: The DictObjectStore containing generated AAS objects
            context: Context string for error messages (e.g., system name)

        Returns:
            True if validation passed (no errors), False otherwise
        """
        return self._validate_object_store(obj_store)

    # ==================== Core Building Methods ====================

    def _extract_interface_properties(self) -> List[Dict]:
        """
        Extract interface properties with schema URLs from config.

        These are used for schema-driven field extraction in Variables submodel.

        Returns:
            List of property dicts with name and schema URL
        """
        interface_config = self.system_config.get(
            'AssetInterfacesDescription', {}) or {}
        mqtt_config = interface_config.get('InterfaceMQTT', {}) or {}
        interaction_config = mqtt_config.get('InteractionMetadata', {}) or {}
        properties_dict = interaction_config.get('properties', {}) or {}

        properties = []
        # Handle dict format: { PropName: {...}, ... }
        for prop_name, prop_config in properties_dict.items():
            if isinstance(prop_config, dict):
                properties.append({
                    'name': prop_name,
                    'schema': prop_config.get('output')
                })

        return properties

    def _build_object_store(self) -> model.DictObjectStore:
        """
        Build the complete AAS object store with all submodels.

        Returns:
            DictObjectStore containing AAS and all submodels
        """
        obj_store: model.DictObjectStore[model.Identifiable] = model.DictObjectStore(
        )

        # Generate main AAS shell
        aas = self.aas_builder.build(self.system_id, self.system_config)
        obj_store.add(aas)

        # Extract interface properties for schema-driven field extraction
        interface_properties = self._extract_interface_properties()

        # Generate all submodels
        submodels = [
            self.asset_interfaces_builder.build(
                self.system_id, self.system_config),
            self.variables_builder.build(
                self.system_id, self.system_config, interface_properties),
            self.parameters_builder.build(self.system_id, self.system_config),
            self.hierarchical_structures_builder.build(
                self.system_id, self.system_config),
            self.capabilities_builder.build(
                self.system_id, self.system_config),
            self.skills_builder.build(self.system_id, self.system_config)
        ]

        for submodel in submodels:
            obj_store.add(submodel)

        return obj_store

    # ==================== Serialization Methods ====================

    def _serialize_to_dict(self, obj_store: model.DictObjectStore) -> Dict:
        """
        Serialize object store to dictionary format.

        Args:
            obj_store: DictObjectStore to serialize

        Returns:
            Dictionary representation of the object store
        """
        json_data = json_serialization.object_store_to_json(obj_store)
        return json.loads(json_data)

    # ==================== Validation Methods ====================

    def _validate_object_store(self, obj_store: model.DictObjectStore) -> bool:
        """
        Validate the generated AAS object store.

        Args:
            obj_store: The DictObjectStore containing generated AAS objects

        Returns:
            True if validation passed (no errors), False otherwise
        """
        print(f"Validating {self.system_id}...")

        validator = AASValidator()
        result = validator.validate(obj_store)

        if not result.is_valid():
            print(f"\n⚠️  Validation errors found:")
            print(result.summary())
            return False

        if result.warnings:
            print(
                f"\n✓ Validation passed (with {len(result.warnings)} warning(s))")
            print("Warnings:")
            for warning in result.warnings:
                print(f"  • {warning}")
        else:
            print(f"✓ Validation passed")

        return True


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
    generator = AASGenerator(
        args.config, delegation_base_url=args.delegation_url)

    # Generate the system
    success = generator.generate_all(args.output, validate=args.validate)

    print("\nGeneration complete!")
    return 0 if success else 1


if __name__ == '__main__':
    exit(main())
