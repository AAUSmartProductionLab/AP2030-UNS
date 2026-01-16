"""
Unified AAS Registration Service

A single service that handles the complete registration workflow:
1. Accepts YAML configurations (instead of full AAS files)
2. Generates topics.json for Operation Delegation Service
3. Creates DataBridge configurations directly from config
4. Generates AAS descriptions using the AAS generator
5. Posts AAS to BaSyx server

This consolidates OperationDelegation config and RegistrationService functionality.
"""

import copy
import json
import logging
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Any, Optional
import yaml

from .config import BaSyxConfig
from .config_parser import ConfigParser, parse_config_file
from .topics_generator import TopicsGenerator
from .databridge_from_config import DataBridgeFromConfig
from .generate_aas import AASGenerator
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
        self.script_dir = Path(__file__).resolve().parent.parent
        self.project_root = self.script_dir.parent
        self.databridge_dir = self.project_root / 'databridge'
        self.topics_json_path = self.project_root / 'OperationDelegation' / 'config' / 'topics.json'
        
        # Generators
        self.topics_generator = TopicsGenerator(str(self.topics_json_path))
        self.databridge_generator = DataBridgeFromConfig(
            mqtt_broker=self.mqtt_broker,
            mqtt_port=self.mqtt_port,
            basyx_url=self.basyx_config.get_internal_url_for_databridge()
        )
    
    def register_from_yaml_config(self, 
                                   config_path: str = None,
                                   config_data: Dict[str, Any] = None,
                                   validate_aas: bool = True,
                                   restart_services: bool = True) -> bool:
        """
        Register an asset from its YAML configuration.
        
        This is the main entry point that performs the complete workflow:
        1. Parse config
        2. Update topics.json
        3. Generate DataBridge configs
        4. Generate AAS
        5. Register with BaSyx
        6. Restart services (optional)
        
        Args:
            config_path: Path to YAML configuration file
            config_data: Already parsed YAML config data (alternative to config_path)
            validate_aas: Whether to validate generated AAS
            restart_services: Whether to restart DataBridge and Operation Delegation containers
            
        Returns:
            True if registration successful
        """
        try:
            # Step 1: Parse configuration
            if config_path:
                logger.info(f"Loading configuration from {config_path}")
                config = parse_config_file(config_path)
                # Also load raw data for AAS generation
                with open(config_path, 'r') as f:
                    config_data = yaml.safe_load(f)
            elif config_data:
                config = ConfigParser(config_data=config_data)
            else:
                raise ValueError("Either config_path or config_data must be provided")
            
            system_id = config.system_id
            logger.info(f"Registering asset: {system_id}")
            
            # Step 2: Update Operation Delegation topics.json
            logger.info("Updating Operation Delegation topics...")
            self.topics_generator.add_from_config(config)
            self.topics_generator.save()
            
            # Step 3: Generate DataBridge configurations
            logger.info("Generating DataBridge configurations...")
            self.databridge_generator.add_from_config(config)
            self.databridge_generator.save_configs(str(self.databridge_dir))
            
            # Step 4: Generate AAS using generate_aas.py
            logger.info("Generating AAS description...")
            aas_json = self._generate_aas(config_data, validate_aas)
            
            if not aas_json:
                logger.error("Failed to generate AAS")
                return False
            
            # Step 5: Register with BaSyx
            logger.info("Registering with BaSyx server...")
            success = self._register_aas_with_basyx(aas_json)
            
            if not success:
                logger.error("Failed to register with BaSyx")
                return False
            
            # Step 6: Restart services (if requested)
            if restart_services:
                logger.info("Restarting services...")
                self._restart_databridge()
                self._restart_operation_delegation()
            else:
                logger.info("Skipping service restarts")
            
            logger.info(f"✓ Successfully registered {system_id}")
            return True
            
        except Exception as e:
            logger.error(f"Registration failed: {e}", exc_info=True)
            return False
    
    def register_multiple_configs(self, config_paths: List[str], validate_aas: bool = True) -> Dict[str, bool]:
        """
        Register multiple assets from YAML configurations.
        
        Args:
            config_paths: List of paths to YAML config files
            validate_aas: Whether to validate generated AAS
            
        Returns:
            Dict mapping config paths to success status
        """
        results = {}
        
        for config_path in config_paths:
            try:
                success = self.register_from_yaml_config(config_path=config_path, validate_aas=validate_aas)
                results[config_path] = success
            except Exception as e:
                logger.error(f"Failed to register {config_path}: {e}")
                results[config_path] = False
        
        # Summary
        successful = sum(1 for s in results.values() if s)
        logger.info(f"Registered {successful}/{len(config_paths)} assets")
        
        return results
    
    def _generate_aas(self, config_data: Dict[str, Any], validate: bool = True) -> Optional[Dict]:
        """
        Generate AAS JSON from configuration data.
        
        Uses the local AASGenerator module.
        
        Returns:
            Generated AAS as dict, or None on failure
        """
        try:
            # Create a temporary config file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
                yaml.dump(config_data, f)
                temp_config_path = f.name
            
            try:
                # Initialize generator (imported at module level)
                generator = AASGenerator(
                    temp_config_path, 
                    delegation_base_url=self.delegation_service_url
                )
                
                # Generate AAS
                system_id = list(config_data.keys())[0]
                system_config = config_data[system_id]
                
                obj_store, aas_dict = generator.generate_system(system_id, system_config, return_store=True)
                
                # Validate if requested
                if validate:
                    generator.validate_generated_aas(obj_store, system_id)
                
                return aas_dict
                
            finally:
                # Clean up temp file
                Path(temp_config_path).unlink(missing_ok=True)
                
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
            
            logger.info(f"Registering {len(shells)} shell(s), {len(submodels)} submodel(s)")
            
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
            response = self.http_client.post(self.basyx_config.aas_repo_url, shell_data)
            
            if self.http_client.is_success(response):
                logger.info(f"Registered AAS shell: {shell_data.get('idShort')}")
                # Register with AAS registry
                self._register_shell_descriptor(shell_data, encoded_id, submodels)
                return True
            elif self.http_client.is_conflict(response):
                # Already exists - delete and re-register
                logger.info(f"Shell exists, updating: {shell_data.get('idShort')}")
                delete_url = f"{self.basyx_config.aas_repo_url}/{encoded_id}"
                self.http_client.delete(delete_url)
                
                # Delete from registry too
                registry_delete_url = f"{self.basyx_config.aas_registry_url}/{encoded_id}"
                self.http_client.delete(registry_delete_url)
                
                # Re-register
                response = self.http_client.post(self.basyx_config.aas_repo_url, shell_data)
                if self.http_client.is_success(response):
                    logger.info(f"Updated AAS shell: {shell_data.get('idShort')}")
                    self._register_shell_descriptor(shell_data, encoded_id, submodels)
                    return True
                else:
                    logger.warning(f"Shell re-registration failed: {response.status_code}")
                    return False
            else:
                logger.warning(f"Shell registration failed: {response.status_code}")
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
            if submodel_data.get('idShort') == 'OfferedCapabilitiyDescription':
                logger.info(f"Debug: CapabilitySet has {len(submodel_data.get('submodelElements', [])[0].get('value', []))} capability containers")
            
            encoded_id = encode_aas_id(submodel_data['id'])
            
            # POST to submodel repository
            response = self.http_client.post(self.basyx_config.submodel_repo_url, submodel_data)
            
            if self.http_client.is_success(response):
                logger.info(f"Registered submodel: {submodel_data.get('idShort')}")
                # Register with submodel registry
                self._register_submodel_descriptor(submodel_data, encoded_id)
                return True
            elif self.http_client.is_conflict(response):
                # Already exists - delete and re-register
                logger.info(f"Submodel exists, updating: {submodel_data.get('idShort')}")
                delete_url = f"{self.basyx_config.submodel_repo_url}/{encoded_id}"
                self.http_client.delete(delete_url)
                
                # Delete from registry too
                registry_delete_url = f"{self.basyx_config.submodel_registry_url}/{encoded_id}"
                self.http_client.delete(registry_delete_url)
                
                # Re-register
                response = self.http_client.post(self.basyx_config.submodel_repo_url, submodel_data)
                if self.http_client.is_success(response):
                    logger.info(f"Updated submodel: {submodel_data.get('idShort')}")
                    self._register_submodel_descriptor(submodel_data, encoded_id)
                    return True
                else:
                    logger.warning(f"Submodel re-registration failed: {response.status_code}")
                    return False
            else:
                logger.warning(f"Submodel registration failed: {response.status_code}")
                # Log detailed error response for debugging
                try:
                    error_detail = response.text if hasattr(response, 'text') else str(response.content)
                    logger.warning(f"Server response: {error_detail[:500]}")
                    logger.warning(f"Failed submodel idShort: {submodel_data.get('idShort')}")
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
            
            response = self.http_client.post(self.basyx_config.concept_desc_url, cd_data)
            
            if self.http_client.is_success(response):
                logger.debug(f"Registered concept description: {cd_data.get('idShort', 'unknown')}")
                return True
            elif self.http_client.is_conflict(response):
                # Already exists - delete and re-register
                encoded_id = encode_aas_id(cd_data['id'])
                delete_url = f"{self.basyx_config.concept_desc_url}/{encoded_id}"
                self.http_client.delete(delete_url)
                
                # Re-register
                response = self.http_client.post(self.basyx_config.concept_desc_url, cd_data)
                if self.http_client.is_success(response):
                    logger.debug(f"Updated concept description: {cd_data.get('idShort', 'unknown')}")
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
                
                if submodel_descriptors:
                    shell_descriptor['submodelDescriptors'] = submodel_descriptors
            
            response = self.http_client.post(self.basyx_config.aas_registry_url, shell_descriptor)
            return response.status_code in [HTTPStatus.OK, HTTPStatus.CREATED, HTTPStatus.CONFLICT]
            
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
            
            response = self.http_client.post(self.basyx_config.submodel_registry_url, submodel_descriptor)
            return response.status_code in [HTTPStatus.OK, HTTPStatus.CREATED, HTTPStatus.CONFLICT]
            
        except Exception as e:
            logger.error(f"Failed to register submodel descriptor: {e}")
            return False
    
    def _preprocess_submodel(self, submodel_data: Dict[str, Any]) -> Dict[str, Any]:
        """Preprocess submodel for BaSyx compatibility"""
        # Don't deep copy - work on original  
        processed = submodel_data
        
        if 'submodelElements' in processed:
            processed['submodelElements'] = self._fix_submodel_elements(processed['submodelElements'])
        
        return processed
    
    def _fix_submodel_elements(self, elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Recursively fix submodel elements for BaSyx compatibility"""
        fixed = []
        
        for element in elements:
            fixed_element = copy.deepcopy(element)  # Deep copy to preserve nested structures
            model_type = element.get('modelType', '')
            
            # Fix File elements
            if model_type == ModelType.FILE:
                if 'valueType' in fixed_element:
                    value_type = fixed_element['valueType']
                    if not value_type.startswith('xs:'):
                        del fixed_element['valueType']
                
                if 'value' in fixed_element and fixed_element['value']:
                    value = fixed_element['value']
                    if value.startswith('/schemas/'):
                        fixed_element['value'] = f"{self.github_pages_base_url}{value}"
            
            # Fix Property elements
            elif model_type == ModelType.PROPERTY:
                if 'valueType' in fixed_element:
                    if not fixed_element['valueType'].startswith('xs:'):
                        fixed_element['valueType'] = 'xs:string'
            
            # Recursively fix collections
            elif model_type == ModelType.SUBMODEL_COLLECTION:
                if 'value' in fixed_element and isinstance(fixed_element['value'], list):
                    fixed_element['value'] = self._fix_submodel_elements(fixed_element['value'])
            
            # Recursively fix SubmodelElementList
            elif model_type == ModelType.SUBMODEL_LIST:
                if 'value' in fixed_element and isinstance(fixed_element['value'], list):
                    fixed_element['value'] = self._fix_submodel_elements(fixed_element['value'])
            
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
            aas_shells = aas_data.get('result', []) if isinstance(aas_data, dict) else []
            
            sm_response = self.http_client.get(self.basyx_config.submodel_repo_url)
            sm_data = sm_response.json() if sm_response.status_code == HTTPStatus.OK else {}
            submodels = sm_data.get('result', []) if isinstance(sm_data, dict) else []
            
            return {
                'aas_shells': aas_shells,
                'submodels': submodels
            }
            
        except Exception as e:
            logger.error(f"Failed to list registered assets: {e}")
            return {'aas_shells': [], 'submodels': []}
