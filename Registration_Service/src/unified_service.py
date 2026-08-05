"""
Unified AAS Registration Service

A single service that handles the complete registration workflow:
1. Accepts JSON configurations matching the ResourceTypeAAS schema
2. Generates topics.json for Operation Delegation Service
3. Creates DataBridge configurations directly from config
4. Generates AAS descriptions via the Pydantic + BaSyx pipeline
5. Posts AAS to BaSyx server

This consolidates OperationDelegation config and RegistrationService functionality.
"""

import copy
import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional

from .config import BaSyxConfig
from .config_parser import parse_config_file, parse_config_data, extract_operation_delegation_entry, extract_databridge_property_mappings
from .topics_generator import TopicsGenerator
from .databridge_from_config import DataBridgeFromConfig
from .aas_idta.builder import build_from_dict  # replaces AASGenerator
from .operation_delegation_api import update_topic_config
from .core import (
    HTTPClient,
    DockerService,
    DEFAULT_MQTT_BROKER,
    DEFAULT_MQTT_PORT,
    DEFAULT_DELEGATION_URL,
    DEFAULT_GITHUB_PAGES_URL,
    HTTPStatus,
    ModelType,
    ContainerNames
)
from .utils import encode_aas_id

logger = logging.getLogger(__name__)


class UnifiedRegistrationService:
    """
    Unified service for complete asset registration from YAML configs.

    Workflow:
    1. Parse YAML config
    2. Update Operation Delegation topics.json
    3. Generate DataBridge configurations
    4. Generate AAS using generate_aas.py
    5. Register AAS with BaSyx server
    6. Restart DataBridge container
    """

    def __init__(self,
                 config: Optional[BaSyxConfig] = None,
                 mqtt_broker: str = DEFAULT_MQTT_BROKER,
                 mqtt_port: int = DEFAULT_MQTT_PORT,
                 databridge_container_name: str = ContainerNames.DATABRIDGE,
                 operation_delegation_container: str = ContainerNames.OPERATION_DELEGATION,
                 delegation_service_url: str = DEFAULT_DELEGATION_URL,
                 github_pages_base_url: str = DEFAULT_GITHUB_PAGES_URL):
        """
        Initialize the unified registration service.

        Args:
            config: BaSyx configuration
            mqtt_broker: MQTT broker hostname/IP
            mqtt_port: MQTT broker port
            databridge_container_name: Name of DataBridge Docker container
            operation_delegation_container: Name of Operation Delegation Docker container
            delegation_service_url: URL of the Operation Delegation Service
            github_pages_base_url: Base URL for schema files on GitHub Pages
        """
        self.basyx_config = config or BaSyxConfig()
        self.mqtt_broker = mqtt_broker
        self.mqtt_port = mqtt_port
        self.databridge_container_name = databridge_container_name
        self.operation_delegation_container = operation_delegation_container
        self.delegation_service_url = delegation_service_url
        self.github_pages_base_url = github_pages_base_url

        # Use new HTTP client and Docker service
        self.http_client = HTTPClient()
        self.docker_service = DockerService()

        # Paths
        # In container: __file__ = /app/src/unified_service.py
        # script_dir = /app (Registration_Service root, which contains src/, OperationDelegation/, etc.)
        self.script_dir = Path(__file__).resolve().parent.parent
        # In container, OperationDelegation is mounted at /app/OperationDelegation
        # so project_root should be the same as script_dir
        self.project_root = self.script_dir
        # Use mounted databridge directory (/databridge) when in container,
        # otherwise use local databridge directory
        if Path('/databridge').exists() and os.access('/databridge', os.W_OK):
            self.databridge_dir = Path('/databridge')
        else:
            self.databridge_dir = self.project_root.parent / 'databridge'
        self.topics_json_path = self.project_root / \
            'OperationDelegation' / 'config' / 'topics.json'

        # Generators
        self.topics_generator = TopicsGenerator(str(self.topics_json_path))
        self.databridge_generator = DataBridgeFromConfig(
            mqtt_broker=self.mqtt_broker,
            mqtt_port=self.mqtt_port,
            basyx_url=self.basyx_config.get_internal_url_for_databridge()
        )

    def register_from_config(
        self,
        config_path: str,
        restart_services: bool = True
    ) -> bool:
        """
        Register an asset from its JSON configuration.

        This is the main entry point that performs the complete workflow:
        1. Parse and validate JSON config against ResourceTypeAAS
        2. Update Operation Delegation topics.json
        3. Generate DataBridge configurations
        4. Generate AAS via Pydantic → BaSyx pipeline
        5. Register with BaSyx server
        6. Restart DataBridge (optional)

        Args:
            config_path: Path to JSON configuration file
            restart_services: Whether to restart DataBridge container

        Returns:
            True if registration successful
        """
        try:
            # Step 1: Parse and validate configuration
            logger.info(f"Loading configuration from {config_path}")
            asset = parse_config_file(config_path)

            system_id = asset.id_short
            logger.info(f"Registering asset: {system_id}")

            # Step 2: Update Operation Delegation config (in-memory + file)
            logger.info("Updating Operation Delegation topics...")
            topics_entry = extract_operation_delegation_entry(asset)
            update_topic_config(system_id, topics_entry)
            self.topics_generator.add_from_config(asset)
            self.topics_generator.save()

            # Step 3: Generate DataBridge configurations
            logger.info("Generating DataBridge configurations...")
            self.databridge_generator.add_from_config(asset)
            self.databridge_generator.save_configs(str(self.databridge_dir))

            # Step 4: Generate AAS (validate + convert in one step)
            logger.info("Generating AAS description...")
            aas_json = self._generate_aas(asset)

            if not aas_json:
                logger.error("Failed to generate AAS")
                return False

            # Step 5: Register with BaSyx
            logger.info("Registering with BaSyx server...")
            success = self._register_aas_with_basyx(aas_json)

            if not success:
                logger.error("Failed to register with BaSyx")
                return False

            # Step 6: Restart DataBridge (if requested)
            if restart_services:
                logger.info("Restarting DataBridge...")
                self._restart_databridge()
            else:
                logger.info("Skipping service restarts")

            logger.info(f"✓ Successfully registered {system_id}")
            return True

        except Exception as e:
            logger.error(f"Registration failed: {e}", exc_info=True)
            return False

    def register_from_data(
        self,
        config_data: Dict[str, Any],
        restart_services: bool = True
    ) -> bool:
        """
        Register an asset from an in-memory JSON config dict.

        Used by the MQTT listener for dynamic registration.

        Args:
            config_data: JSON config dict matching ResourceTypeAAS schema
            restart_services: Whether to restart DataBridge container

        Returns:
            True if registration successful
        """
        try:
            asset = parse_config_data(config_data)
            system_id = asset.id_short
            logger.info(f"Registering asset: {system_id}")

            topics_entry = extract_operation_delegation_entry(asset)
            update_topic_config(system_id, topics_entry)
            self.topics_generator.add_from_config(asset)
            self.topics_generator.save()

            self.databridge_generator.add_from_config(asset)
            self.databridge_generator.save_configs(str(self.databridge_dir))

            aas_json = self._generate_aas(asset)
            if not aas_json:
                return False

            success = self._register_aas_with_basyx(aas_json)
            if not success:
                return False

            if restart_services:
                self._restart_databridge()

            logger.info(f"✓ Successfully registered {system_id}")
            return True

        except Exception as e:
            logger.error(f"Registration failed: {e}", exc_info=True)
            return False

    def register_multiple_configs(self, config_paths: List[str]) -> Dict[str, bool]:
        """
        Register multiple assets from JSON configurations.

        Args:
            config_paths: List of paths to JSON config files

        Returns:
            Dict mapping config paths to success status
        """
        results = {}

        for config_path in config_paths:
            try:
                success = self.register_from_config(config_path=config_path)
                results[config_path] = success
            except Exception as e:
                logger.error(f"Failed to register {config_path}: {e}")
                results[config_path] = False

        successful = sum(1 for s in results.values() if s)
        logger.info(f"Registered {successful}/{len(config_paths)} assets")

        return results

    def _generate_aas(self, asset) -> Optional[Dict]:
        """
        Convert a validated ResourceTypeAAS instance to BaSyx JSON.

        Args:
            asset: Validated ResourceTypeAAS Pydantic instance

        Returns:
            BaSyx-compatible JSON dict, or None on failure
        """
        try:
            from basyx.aas.adapter.json import json_serialization

            # Convert Pydantic model directly (no raw dict needed)
            obj_store = build_from_dict(asset.model_dump())

            json_str = json_serialization.object_store_to_json(obj_store)
            return json.loads(json_str)

        except Exception as e:
            logger.error(f"Failed to generate AAS: {e}", exc_info=True)
            return None

    def _register_aas_with_basyx(self, aas_json: Dict[str, Any]) -> bool:
        """
        Register generated AAS JSON with BaSyx server.

        Args:
            aas_json: AAS JSON data from generator

        Returns:
            True if registration successful
        """
        try:
            # Extract components from AAS JSON
            shells = aas_json.get('assetAdministrationShells', [])
            submodels = aas_json.get('submodels', [])
            concept_descriptions = aas_json.get('conceptDescriptions', [])

            logger.info(
                f"Registering {len(shells)} shell(s), {len(submodels)} submodel(s)")

            # Register concept descriptions first
            for cd in concept_descriptions:
                self._register_concept_description(cd)

            # Register submodels
            for submodel in submodels:
                self._register_submodel(submodel)

            # Register shells
            for shell in shells:
                self._register_shell(shell, submodels)

            return True

        except Exception as e:
            logger.error(f"BaSyx registration failed: {e}")
            return False

    def _register_shell(self, shell_data: Dict[str, Any], submodels: List[Dict[str, Any]]) -> bool:
        """Register AAS shell with BaSyx server"""
        try:
            if 'modelType' not in shell_data:
                shell_data['modelType'] = ModelType.AAS

            encoded_id = encode_aas_id(shell_data['id'])

            # POST to AAS repository
            response = self.http_client.post(
                self.basyx_config.aas_repo_url, shell_data)

            if self.http_client.is_success(response):
                logger.info(
                    f"Registered AAS shell: {shell_data.get('idShort')}")
                # Register with AAS registry
                self._register_shell_descriptor(
                    shell_data, encoded_id, submodels)
                return True
            elif self.http_client.is_conflict(response):
                # Already exists - delete and re-register
                logger.info(
                    f"Shell exists, updating: {shell_data.get('idShort')}")
                delete_url = f"{self.basyx_config.aas_repo_url}/{encoded_id}"
                self.http_client.delete(delete_url)

                # Delete from registry too
                registry_delete_url = f"{self.basyx_config.aas_registry_url}/{encoded_id}"
                self.http_client.delete(registry_delete_url)

                # Re-register
                response = self.http_client.post(
                    self.basyx_config.aas_repo_url, shell_data)
                if self.http_client.is_success(response):
                    logger.info(
                        f"Updated AAS shell: {shell_data.get('idShort')}")
                    self._register_shell_descriptor(
                        shell_data, encoded_id, submodels)
                    return True
                else:
                    logger.warning(
                        f"Shell re-registration failed: {response.status_code}")
                    return False
            else:
                logger.warning(
                    f"Shell registration failed: {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"Failed to register shell: {e}")
            return False

    def _register_submodel(self, submodel_data: Dict[str, Any]) -> bool:
        """Register submodel with BaSyx server"""
        try:
            if 'modelType' not in submodel_data:
                submodel_data['modelType'] = ModelType.SUBMODEL

            # Preprocess to fix any compatibility issues
            submodel_data = self._preprocess_submodel(submodel_data)

            # Debug logging for capabilities submodel
            if submodel_data.get('idShort') == 'OfferedCapabilityDescription':
                logger.info(
                    f"Debug: CapabilitySet has {len(submodel_data.get('submodelElements', [])[0].get('value', []))} capability containers")

            encoded_id = encode_aas_id(submodel_data['id'])

            # POST to submodel repository
            response = self.http_client.post(
                self.basyx_config.submodel_repo_url, submodel_data)

            if self.http_client.is_success(response):
                logger.info(
                    f"Registered submodel: {submodel_data.get('idShort')}")
                # Register with submodel registry
                self._register_submodel_descriptor(submodel_data, encoded_id)
                return True
            elif self.http_client.is_conflict(response):
                # Already exists - delete and re-register
                logger.info(
                    f"Submodel exists, updating: {submodel_data.get('idShort')}")
                delete_url = f"{self.basyx_config.submodel_repo_url}/{encoded_id}"
                self.http_client.delete(delete_url)

                # Delete from registry too
                registry_delete_url = f"{self.basyx_config.submodel_registry_url}/{encoded_id}"
                self.http_client.delete(registry_delete_url)

                # Re-register
                response = self.http_client.post(
                    self.basyx_config.submodel_repo_url, submodel_data)
                if self.http_client.is_success(response):
                    logger.info(
                        f"Updated submodel: {submodel_data.get('idShort')}")
                    self._register_submodel_descriptor(
                        submodel_data, encoded_id)
                    return True
                else:
                    logger.warning(
                        f"Submodel re-registration failed: {response.status_code}")
                    return False
            else:
                logger.warning(
                    f"Submodel registration failed: {response.status_code}")
                # Log detailed error response for debugging
                try:
                    error_detail = response.text if hasattr(
                        response, 'text') else str(response.content)
                    logger.warning(f"Server response: {error_detail[:500]}")
                    logger.warning(
                        f"Failed submodel idShort: {submodel_data.get('idShort')}")
                except:
                    pass
                return False

        except Exception as e:
            logger.error(f"Failed to register submodel: {e}")
            return False

    def _register_concept_description(self, cd_data: Dict[str, Any]) -> bool:
        """Register concept description with BaSyx server"""
        try:
            if 'modelType' not in cd_data:
                cd_data['modelType'] = ModelType.CONCEPT_DESCRIPTION

            response = self.http_client.post(
                self.basyx_config.concept_desc_url, cd_data)

            if self.http_client.is_success(response):
                logger.debug(
                    f"Registered concept description: {cd_data.get('idShort', 'unknown')}")
                return True
            elif self.http_client.is_conflict(response):
                # Already exists - delete and re-register
                encoded_id = encode_aas_id(cd_data['id'])
                delete_url = f"{self.basyx_config.concept_desc_url}/{encoded_id}"
                self.http_client.delete(delete_url)

                # Re-register
                response = self.http_client.post(
                    self.basyx_config.concept_desc_url, cd_data)
                if self.http_client.is_success(response):
                    logger.debug(
                        f"Updated concept description: {cd_data.get('idShort', 'unknown')}")
                    return True
            return False

        except Exception as e:
            logger.debug(f"Failed to register concept description: {e}")
            return False

    def _register_shell_descriptor(self, shell_data: Dict[str, Any],
                                   encoded_id: str,
                                   submodels: List[Dict[str, Any]]) -> bool:
        """Register shell descriptor in AAS registry"""
        try:
            external_url = self.basyx_config.get_external_url()
            
            logger.info(f"Registering shell descriptor with {len(submodels)} submodels")

            shell_descriptor = {
                "id": shell_data['id'],
                "idShort": shell_data['idShort'],
                "assetKind": shell_data.get('assetInformation', {}).get('assetKind', 'Instance'),
                "endpoints": [{
                    "interface": "AAS-3.0",
                    "protocolInformation": {
                        "href": f"{external_url}/shells/{encoded_id}",
                        "endpointProtocol": "HTTP"
                    }
                }]
            }

            # Add globalAssetId
            if 'assetInformation' in shell_data and 'globalAssetId' in shell_data['assetInformation']:
                shell_descriptor['globalAssetId'] = shell_data['assetInformation']['globalAssetId']

            # Add submodel descriptors
            if submodels:
                submodel_descriptors = []
                for sm in submodels:
                    if sm and sm.get('id'):
                        sm_encoded_id = encode_aas_id(sm['id'])
                        sm_descriptor = {
                            "id": sm['id'],
                            "idShort": sm['idShort'],
                            "endpoints": [{
                                "interface": "SUBMODEL-3.0",
                                "protocolInformation": {
                                    "href": f"{external_url}/submodels/{sm_encoded_id}",
                                    "endpointProtocol": "HTTP"
                                }
                            }]
                        }
                        if 'semanticId' in sm:
                            sm_descriptor['semanticId'] = sm['semanticId']
                        submodel_descriptors.append(sm_descriptor)
                        logger.debug(f"Added submodel descriptor: {sm['idShort']}")
                    else:
                        logger.warning(f"Skipping invalid submodel: {sm}")

                logger.info(f"Built {len(submodel_descriptors)} submodel descriptors")
                if submodel_descriptors:
                    shell_descriptor['submodelDescriptors'] = submodel_descriptors

            response = self.http_client.post(
                self.basyx_config.aas_registry_url, shell_descriptor)
            logger.info(f"Shell descriptor registration response: {response.status_code}")
            
            if self.http_client.is_conflict(response):
                # Already exists - delete and re-register
                logger.info(f"Shell descriptor exists, updating...")
                delete_url = f"{self.basyx_config.aas_registry_url}/{encoded_id}"
                self.http_client.delete(delete_url)
                
                # Re-register
                response = self.http_client.post(
                    self.basyx_config.aas_registry_url, shell_descriptor)
                logger.info(f"Shell descriptor re-registration response: {response.status_code}")
            
            return response.status_code in [HTTPStatus.OK, HTTPStatus.CREATED]

        except Exception as e:
            logger.error(f"Failed to register shell descriptor: {e}")
            return False

    def _register_submodel_descriptor(self, submodel_data: Dict[str, Any], encoded_id: str) -> bool:
        """Register submodel descriptor in submodel registry"""
        try:
            external_url = self.basyx_config.get_external_url()

            submodel_descriptor = {
                "id": submodel_data['id'],
                "idShort": submodel_data['idShort'],
                "endpoints": [{
                    "interface": "SUBMODEL-3.0",
                    "protocolInformation": {
                        "href": f"{external_url}/submodels/{encoded_id}",
                        "endpointProtocol": "HTTP"
                    }
                }]
            }

            if 'semanticId' in submodel_data:
                submodel_descriptor['semanticId'] = submodel_data['semanticId']

            response = self.http_client.post(
                self.basyx_config.submodel_registry_url, submodel_descriptor)
            return response.status_code in [HTTPStatus.OK, HTTPStatus.CREATED, HTTPStatus.CONFLICT]

        except Exception as e:
            logger.error(f"Failed to register submodel descriptor: {e}")
            return False

    def _preprocess_submodel(self, submodel_data: Dict[str, Any]) -> Dict[str, Any]:
        """Preprocess submodel for BaSyx compatibility"""
        # Don't deep copy - work on original
        processed = submodel_data

        if 'submodelElements' in processed:
            processed['submodelElements'] = self._fix_submodel_elements(
                processed['submodelElements'])

        return processed

    def _fix_submodel_elements(self, elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Recursively fix submodel elements for BaSyx compatibility"""
        fixed = []

        for element in elements:
            # Deep copy to preserve nested structures
            fixed_element = copy.deepcopy(element)
            model_type = element.get('modelType', '')

            # Fix File elements
            if model_type == ModelType.FILE:
                if 'valueType' in fixed_element:
                    value_type = fixed_element['valueType']
                    if not value_type.startswith('xs:'):
                        del fixed_element['valueType']

                if 'value' in fixed_element and fixed_element['value']:
                    value = fixed_element['value']
                    if value.startswith('/MQTTSchema'):
                        fixed_element['value'] = f"{self.github_pages_base_url}{value}"

            # Fix Property elements
            elif model_type == ModelType.PROPERTY:
                if 'valueType' in fixed_element:
                    if not fixed_element['valueType'].startswith('xs:'):
                        fixed_element['valueType'] = 'xs:string'

            # Recursively fix collections
            elif model_type == ModelType.SUBMODEL_COLLECTION:
                if 'value' in fixed_element and isinstance(fixed_element['value'], list):
                    fixed_element['value'] = self._fix_submodel_elements(
                        fixed_element['value'])

            # Recursively fix SubmodelElementList
            elif model_type == ModelType.SUBMODEL_LIST:
                if 'value' in fixed_element and isinstance(fixed_element['value'], list):
                    fixed_element['value'] = self._fix_submodel_elements(
                        fixed_element['value'])

            fixed.append(fixed_element)

        return fixed

    def _restart_databridge(self) -> bool:
        """Restart DataBridge container"""
        return self.docker_service.restart_databridge()

    def _restart_operation_delegation(self) -> bool:
        """Restart Operation Delegation container"""
        return self.docker_service.restart_operation_delegation()

    def list_registered_assets(self) -> Dict[str, Any]:
        """List all registered AAS and submodels"""
        try:
            aas_response = self.http_client.get(self.basyx_config.aas_repo_url)
            aas_data = aas_response.json() if aas_response.status_code == HTTPStatus.OK else {}
            aas_shells = aas_data.get('result', []) if isinstance(
                aas_data, dict) else []

            sm_response = self.http_client.get(
                self.basyx_config.submodel_repo_url)
            sm_data = sm_response.json() if sm_response.status_code == HTTPStatus.OK else {}
            submodels = sm_data.get('result', []) if isinstance(
                sm_data, dict) else []

            return {
                'aas_shells': aas_shells,
                'submodels': submodels
            }

        except Exception as e:
            logger.error(f"Failed to list registered assets: {e}")
            return {'aas_shells': [], 'submodels': []}
