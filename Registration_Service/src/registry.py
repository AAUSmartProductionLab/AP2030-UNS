"""
BaSyx Registration Service

Handles registration of AAS shells, submodels, and concept descriptions
with BaSyx server and registries.
"""

import base64
import json
import logging
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Optional
import requests

from .config import BaSyxConfig
from .parsers import AASXParser
from .databridge import DataBridgeConfigGenerator
from .interface_parser import MQTTInterfaceParser

logger = logging.getLogger(__name__)


class BaSyxRegistrationService:
    """Main service for registering AAS and configuring databridge"""

    def __init__(self, config: Optional[BaSyxConfig] = None, 
                 mqtt_broker: str = "hivemq-broker",
                 mqtt_port: int = 1883,
                 databridge_container_name: str = "databridge",
                 github_pages_base_url: str = "https://aausmartproductionlab.github.io/AP2030-UNS"):
        self.basyx_config = config or BaSyxConfig()
        self.mqtt_broker = mqtt_broker
        self.mqtt_port = mqtt_port
        self.databridge_container_name = databridge_container_name
        self.github_pages_base_url = github_pages_base_url
        self.session = requests.Session()
        self.session.headers.update({'Content-Type': 'application/json'})

    def register_aasx(self, aasx_path: str) -> bool:
        """Register AASX file and configure databridge"""
        try:
            logger.info(f"Starting registration of {aasx_path}")

            # Parse AASX file
            parser = AASXParser(aasx_path)
            aas_data = parser.parse()

            logger.info(
                f"Found {len(aas_data['aas_shells'])} AAS shells and {len(aas_data['submodels'])} submodels")

            # Register submodels first
            for submodel in aas_data['submodels']:
                self._register_submodel(submodel)

            # Register AAS shells with submodel references
            for shell in aas_data['aas_shells']:
                self._register_aas_shell_with_submodels(
                    shell, aas_data['submodels'])

            # Generate and save databridge configurations
            self._generate_databridge_configs(
                aas_data['submodels'], self.mqtt_broker, None, None)

            logger.info("Registration completed successfully!")
            return True

        except Exception as e:
            logger.error(f"Registration failed: {e}")
            return False

    def register_from_json(self, json_path: str) -> bool:
        """Register AAS from JSON file with automatic topic extraction from InterfaceMQTT"""
        try:
            logger.info(f"Starting registration from JSON: {json_path}")

            # Load JSON file
            with open(json_path, 'r', encoding='utf-8') as f:
                registration_data = json.load(f)

            # Support multiple input formats
            # Format 1: Direct AAS structure (assetAdministrationShells, submodels)
            # Format 2: Wrapped in 'aas_data' key with optional 'topic_mappings'
            if 'assetAdministrationShells' in registration_data:
                # Direct format
                shells = registration_data.get('assetAdministrationShells', [])
                submodels = registration_data.get('submodels', [])
                manual_topic_mappings = {}
            else:
                # Wrapped format
                aas_data = registration_data.get('aas_data', {})
                shells = aas_data.get('assetAdministrationShells', [])
                if not shells:
                    # Fallback to single shell format
                    shell = aas_data.get('aas_shell', {})
                    if shell:
                        shells = [shell]
                
                submodels = aas_data.get('submodels', [])
                manual_topic_mappings = registration_data.get('topic_mappings', {})

            logger.info(f"Found {len(shells)} AAS shell(s) and {len(submodels)} submodels")

            # Parse InterfaceMQTT submodel to extract MQTT topics automatically
            interface_parser = MQTTInterfaceParser()
            interface_info = interface_parser.parse_interface_submodels(submodels)
            
            # Extract topic mappings from interface
            auto_topic_mappings = interface_parser.extract_topic_mappings(submodels)
            
            # Update broker info if found in interface
            if interface_info.get('broker_host'):
                logger.info(f"Using MQTT broker from InterfaceMQTT: {interface_info['broker_host']}:{interface_info['broker_port']}")
                self.mqtt_broker = interface_info['broker_host']
                self.mqtt_port = interface_info['broker_port']
            
            # Merge manual and auto-extracted topic mappings (manual takes precedence)
            topic_mappings = {**auto_topic_mappings, **manual_topic_mappings}
            
            if auto_topic_mappings:
                logger.info(f"Extracted {len(auto_topic_mappings)} topic mappings from InterfaceMQTT")
                for topic, path in list(auto_topic_mappings.items())[:5]:  # Show first 5
                    logger.info(f"  {topic} -> {path}")
                if len(auto_topic_mappings) > 5:
                    logger.info(f"  ... and {len(auto_topic_mappings) - 5} more")

            # Register concept descriptions first (if any semanticIds exist)
            self._register_concept_descriptions_from_submodels(submodels)

            # Register submodels
            for submodel in submodels:
                self._register_submodel(submodel)

            # Register AAS shells with submodel references
            for shell in shells:
                if shell:
                    self._register_aas_shell_with_submodels(shell, submodels)

            # Generate and save databridge configurations with topic mappings
            self._generate_databridge_configs(
                submodels, self.mqtt_broker, topic_mappings, interface_info)

            # Restart databridge container
            self._restart_databridge()

            logger.info("Registration completed successfully!")
            return True

        except Exception as e:
            logger.error(f"Registration failed: {e}")
            return False

    def _register_aas_shell_with_submodels(self, shell_data: Dict[str, Any], submodels: List[Dict[str, Any]]) -> bool:
        """Register AAS shell with proper submodel references"""
        try:
            # Create submodel references
            submodel_refs = []
            for submodel in submodels:
                if submodel and submodel.get('id'):
                    submodel_ref = {
                        "keys": [
                            {
                                "type": "Submodel",
                                "value": submodel['id']
                            }
                        ],
                        "type": "ModelReference"
                    }
                    submodel_refs.append(submodel_ref)

            # Upload to repository with submodel references
            shell_repo_data = {
                "modelType": "AssetAdministrationShell",
                "id": shell_data['id'],
                "idShort": shell_data['idShort'],
                "assetInformation": shell_data.get('assetInformation', {"assetKind": "Instance"}),
                "submodels": submodel_refs
            }

            encoded_id = base64.b64encode(shell_data['id'].encode()).decode()
            repo_response = self._make_request(
                'POST', self.basyx_config.aas_repo_url, shell_repo_data)

            logger.info(
                f"Registered AAS shell in repository with {len(submodel_refs)} submodel references: {shell_data['idShort']}")
            
            # Also register shell descriptor in AAS Registry with submodel descriptors
            self._register_shell_descriptor(shell_data, encoded_id, submodels)

            return True

        except Exception as e:
            logger.error(
                f"Failed to register AAS shell {shell_data.get('idShort', 'unknown')}: {e}")
            return False

    def _register_submodel(self, submodel_data: Dict[str, Any]) -> bool:
        """Register submodel with BaSyx server"""
        try:
            # Preprocess submodel to fix File elements
            processed_submodel = self._preprocess_submodel_for_registration(submodel_data)
            
            # Add modelType for BaSyx 2.0 compatibility
            submodel_repo_data = {
                "modelType": "Submodel",
                **processed_submodel
            }

            # Upload to repository (BaSyx 2.0 pattern)
            encoded_id = base64.b64encode(
                submodel_data['id'].encode()).decode()
            repo_response = self._make_request(
                'POST', self.basyx_config.submodel_repo_url, submodel_repo_data)

            logger.info(f"Registered submodel in repository: {submodel_data['idShort']}")
            
            # Upload file attachments (schemas, etc.) for File elements
            self._upload_file_attachments(submodel_data, encoded_id)
            
            # Also register submodel descriptor in Submodel Registry
            self._register_submodel_descriptor(submodel_data, encoded_id)

            return True

        except Exception as e:
            logger.error(
                f"Failed to register submodel {submodel_data.get('idShort', 'unknown')}: {e}")
            return False
    
    def _preprocess_submodel_for_registration(self, submodel_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Preprocess submodel to fix incompatibilities with BaSyx server.
        
        Issues fixed:
        - File elements: Convert local paths to GitHub Pages URLs
        - File elements: Remove non-XSD valueType
        - Property elements: Ensure valid XSD valueType
        - Nested SubmodelElementCollections
        """
        import copy
        processed = copy.deepcopy(submodel_data)
        
        # Fix submodel elements recursively
        if 'submodelElements' in processed:
            processed['submodelElements'] = self._fix_submodel_elements(
                processed['submodelElements'], 
                self.github_pages_base_url
            )
        
        return processed
    
    def _fix_submodel_elements(self, elements: List[Dict[str, Any]], github_pages_base_url: str = "https://aausmartproductionlab.github.io/AP2030-UNS") -> List[Dict[str, Any]]:
        """
        Recursively fix submodel elements.
        
        Fixes:
        - File elements: Convert local paths to GitHub Pages URLs
        - Property elements: Ensure valid XSD valueType
        """
        fixed_elements = []
        
        for element in elements:
            fixed_element = element.copy()
            model_type = element.get('modelType', '')
            
            # Fix File elements
            if model_type == 'File':
                # Remove invalid valueType if present
                if 'valueType' in fixed_element:
                    value_type = fixed_element['valueType']
                    if not value_type.startswith('xs:'):
                        logger.debug(f"Removing invalid valueType '{value_type}' from File element '{fixed_element.get('idShort')}'")
                        del fixed_element['valueType']
                
                # Convert local schema paths to GitHub Pages URLs
                if 'value' in fixed_element:
                    value = fixed_element['value']
                    if value and value.startswith('/schemas/'):
                        # Convert /schemas/command.schema.json to full URL
                        github_url = f"{github_pages_base_url}{value}"
                        logger.info(f"Converting File path '{value}' to URL: {github_url}")
                        fixed_element['value'] = github_url
            
            # Fix Property elements - ensure valueType is valid XSD type
            elif model_type == 'Property':
                if 'valueType' in fixed_element:
                    value_type = fixed_element['valueType']
                    # Replace non-XSD types with xs:string
                    if not value_type.startswith('xs:'):
                        logger.debug(f"Replacing invalid valueType '{value_type}' with 'xs:string' for Property '{fixed_element.get('idShort')}'")
                        fixed_element['valueType'] = 'xs:string'
                        
                        # If this is a schema property, also convert the value to URL
                        if fixed_element.get('idShort') == 'schema' and 'value' in fixed_element:
                            schema_value = fixed_element['value']
                            if schema_value and schema_value.startswith('/schemas/'):
                                github_url = f"{github_pages_base_url}{schema_value}"
                                logger.info(f"Converting schema property path '{schema_value}' to URL: {github_url}")
                                fixed_element['value'] = github_url
            
            # Recursively process SubmodelElementCollections
            elif model_type == 'SubmodelElementCollection':
                if 'value' in fixed_element and isinstance(fixed_element['value'], list):
                    fixed_element['value'] = self._fix_submodel_elements(fixed_element['value'], github_pages_base_url)
            
            fixed_elements.append(fixed_element)
        
        return fixed_elements
    
    def _upload_file_attachments(self, submodel_data: Dict[str, Any], encoded_submodel_id: str):
        """
        Upload file attachments for File elements in the submodel.
        Searches for schema files in ../schemas/ directory and uploads them to the AAS.
        """
        # Get the schemas directory (next to Registration_Service)
        script_dir = Path(__file__).resolve().parent.parent
        schemas_dir = script_dir.parent / 'schemas'
        
        if not schemas_dir.exists():
            logger.warning(f"Schemas directory not found: {schemas_dir}")
            return
        
        # Find all File elements recursively
        file_elements = self._find_file_elements(submodel_data.get('submodelElements', []))
        
        if not file_elements:
            logger.debug(f"No File elements found in submodel {submodel_data.get('idShort')}")
            return
        
        logger.info(f"Found {len(file_elements)} File element(s) in submodel, checking for attachments...")
        
        uploaded_count = 0
        for file_path, file_element in file_elements:
            file_value = file_element.get('value', '')
            
            if not file_value:
                continue
            
            # Extract filename from path (e.g., /schemas/command.schema.json -> command.schema.json)
            if file_value.startswith('/schemas/'):
                filename = file_value.replace('/schemas/', '')
            elif file_value.startswith('schemas/'):
                filename = file_value.replace('schemas/', '')
            else:
                filename = Path(file_value).name
            
            # Find the file in schemas directory
            schema_file = schemas_dir / filename
            
            if schema_file.exists():
                success = self._upload_file_to_submodel_element(
                    encoded_submodel_id, 
                    file_path, 
                    schema_file,
                    file_element.get('contentType', 'application/json')
                )
                if success:
                    uploaded_count += 1
            else:
                logger.debug(f"Schema file not found: {schema_file}")
        
        if uploaded_count > 0:
            logger.info(f"✓ Uploaded {uploaded_count} file attachment(s) to submodel")
    
    def _find_file_elements(self, elements: List[Dict[str, Any]], parent_path: str = "") -> List[tuple]:
        """
        Recursively find all File elements in submodel elements.
        Returns list of (idShortPath, element_dict) tuples.
        """
        file_elements = []
        
        for element in elements:
            id_short = element.get('idShort', '')
            current_path = f"{parent_path}.{id_short}" if parent_path else id_short
            model_type = element.get('modelType', '')
            
            if model_type == 'File':
                file_elements.append((current_path, element))
            elif model_type == 'SubmodelElementCollection':
                # Recursively search in collections
                nested_elements = element.get('value', [])
                if isinstance(nested_elements, list):
                    file_elements.extend(self._find_file_elements(nested_elements, current_path))
        
        return file_elements
    
    def _upload_file_to_submodel_element(self, encoded_submodel_id: str, id_short_path: str, 
                                         file_path: Path, content_type: str) -> bool:
        """
        Upload a file to a File submodel element using BaSyx API.
        
        BaSyx API: PUT /submodels/{submodelId}/submodel-elements/{idShortPath}/attachment
        """
        try:
            # URL encode the idShortPath
            import urllib.parse
            encoded_path = urllib.parse.quote(id_short_path, safe='')
            
            # Construct the upload URL
            upload_url = f"{self.basyx_config.base_url}/submodels/{encoded_submodel_id}/submodel-elements/{encoded_path}/attachment"
            
            # Read the file content
            with open(file_path, 'rb') as f:
                file_content = f.read()
            
            # Upload using PUT request with file content
            response = requests.put(
                upload_url,
                data=file_content,
                headers={
                    'Content-Type': content_type,
                    'Accept': 'application/json'
                }
            )
            
            if response.status_code in [200, 201, 204]:
                logger.info(f"  ✓ Uploaded {file_path.name} to {id_short_path}")
                return True
            else:
                logger.warning(f"  ✗ Failed to upload {file_path.name}: HTTP {response.status_code} - {response.text[:200]}")
                return False
                
        except Exception as e:
            logger.warning(f"  ✗ Error uploading {file_path.name}: {e}")
            return False

    def _register_shell_descriptor(self, shell_data: Dict[str, Any], encoded_id: str, submodels: List[Dict[str, Any]] = None) -> bool:
        """Register AAS shell descriptor in the AAS Registry (port 8082) with submodel descriptors"""
        try:
            # Extract external URL from basyx_config or use default
            external_url = self.basyx_config.base_url.replace("localhost", "192.168.0.104")
            
            # Create shell descriptor for registry
            shell_descriptor = {
                "id": shell_data['id'],
                "idShort": shell_data['idShort'],
                "assetKind": shell_data.get('assetInformation', {}).get('assetKind', 'Instance'),
                "endpoints": [
                    {
                        "interface": "AAS-3.0",
                        "protocolInformation": {
                            "href": f"{external_url}/shells/{encoded_id}",
                            "endpointProtocol": "HTTP"
                        }
                    }
                ]
            }
            
            # Add globalAssetId if available
            if 'assetInformation' in shell_data and 'globalAssetId' in shell_data['assetInformation']:
                shell_descriptor['globalAssetId'] = shell_data['assetInformation']['globalAssetId']
            
            # Add submodel descriptors if submodels are provided
            if submodels:
                submodel_descriptors = []
                for submodel in submodels:
                    if submodel and submodel.get('id'):
                        sm_encoded_id = base64.b64encode(submodel['id'].encode()).decode()
                        sm_descriptor = {
                            "id": submodel['id'],
                            "idShort": submodel['idShort'],
                            "endpoints": [
                                {
                                    "interface": "SUBMODEL-3.0",
                                    "protocolInformation": {
                                        "href": f"{external_url}/submodels/{sm_encoded_id}",
                                        "endpointProtocol": "HTTP"
                                    }
                                }
                            ]
                        }
                        # Add semanticId if available
                        if 'semanticId' in submodel:
                            sm_descriptor['semanticId'] = submodel['semanticId']
                        
                        submodel_descriptors.append(sm_descriptor)
                
                if submodel_descriptors:
                    shell_descriptor['submodelDescriptors'] = submodel_descriptors
                    logger.info(f"Adding {len(submodel_descriptors)} submodel descriptors to shell descriptor")
            
            # POST to AAS Registry
            registry_response = self._make_request(
                'POST', self.basyx_config.aas_registry_url, shell_descriptor)
            
            if registry_response.status_code in [200, 201, 409]:
                logger.info(f"Registered shell descriptor in AAS Registry: {shell_data['idShort']}")
                return True
            else:
                logger.warning(f"Failed to register shell descriptor, status: {registry_response.status_code}")
                return False

        except Exception as e:
            logger.error(f"Failed to register shell descriptor: {e}")
            return False

    def _register_submodel_descriptor(self, submodel_data: Dict[str, Any], encoded_id: str) -> bool:
        """Register submodel descriptor in the Submodel Registry (port 8083)"""
        try:
            # Extract external URL from basyx_config or use default
            external_url = self.basyx_config.base_url.replace("localhost", "192.168.0.104")
            
            # Create submodel descriptor for registry
            submodel_descriptor = {
                "id": submodel_data['id'],
                "idShort": submodel_data['idShort'],
                "endpoints": [
                    {
                        "interface": "SUBMODEL-3.0",
                        "protocolInformation": {
                            "href": f"{external_url}/submodels/{encoded_id}",
                            "endpointProtocol": "HTTP"
                        }
                    }
                ]
            }
            
            # Add semanticId if available
            if 'semanticId' in submodel_data:
                submodel_descriptor['semanticId'] = submodel_data['semanticId']
            
            # POST to Submodel Registry
            registry_response = self._make_request(
                'POST', self.basyx_config.submodel_registry_url, submodel_descriptor)
            
            if registry_response.status_code in [200, 201, 409]:
                logger.info(f"Registered submodel descriptor in Submodel Registry: {submodel_data['idShort']}")
                return True
            else:
                logger.warning(f"Failed to register submodel descriptor, status: {registry_response.status_code}")
                return False

        except Exception as e:
            logger.error(f"Failed to register submodel descriptor: {e}")
            return False

    def _register_concept_descriptions_from_submodels(self, submodels: List[Dict[str, Any]]):
        """Extract and register concept descriptions from submodels"""
        try:
            concept_descriptions = {}
            
            # Extract unique semanticIds from submodels and their elements
            for submodel in submodels:
                # Submodel semanticId
                if 'semanticId' in submodel:
                    semantic_id = submodel['semanticId']['keys'][0]['value']
                    if semantic_id not in concept_descriptions:
                        concept_descriptions[semantic_id] = {
                            "modelType": "ConceptDescription",
                            "id": semantic_id,
                            "idShort": submodel.get('idShort', 'ConceptDescription'),
                            "description": [
                                {
                                    "language": "en",
                                    "text": f"Concept description for {submodel.get('idShort', 'submodel')}"
                                }
                            ]
                        }
                
                # Property semanticIds
                for element in submodel.get('submodelElements', []):
                    if 'semanticId' in element:
                        semantic_id = element['semanticId']['keys'][0]['value']
                        if semantic_id not in concept_descriptions:
                            concept_descriptions[semantic_id] = {
                                "modelType": "ConceptDescription",
                                "id": semantic_id,
                                "idShort": element.get('idShort', 'ConceptDescription'),
                                "description": [
                                    {
                                        "language": "en",
                                        "text": f"Concept description for {element.get('idShort', 'property')}"
                                    }
                                ]
                            }
            
            # Register each concept description
            if concept_descriptions:
                logger.info(f"Registering {len(concept_descriptions)} concept descriptions")
                for cd_id, cd_data in concept_descriptions.items():
                    self._register_concept_description(cd_data)
            
        except Exception as e:
            logger.warning(f"Failed to register concept descriptions: {e}")

    def _register_concept_description(self, cd_data: Dict[str, Any]) -> bool:
        """Register a concept description in the repository"""
        try:
            # POST to concept descriptions endpoint
            cd_url = f"{self.basyx_config.base_url}/concept-descriptions"
            response = self._make_request('POST', cd_url, cd_data)
            
            if response.status_code in [200, 201, 409]:
                logger.info(f"Registered concept description: {cd_data['idShort']}")
                return True
            else:
                logger.debug(f"Concept description registration status: {response.status_code}")
                return False
                
        except Exception as e:
            logger.debug(f"Failed to register concept description {cd_data.get('idShort', 'unknown')}: {e}")
            return False

    def _generate_databridge_configs(self, submodels: List[Dict[str, Any]], mqtt_broker: str, topic_mappings: Optional[Dict[str, str]] = None, interface_info: Optional[Dict[str, Any]] = None):
        """Generate and save databridge configuration files with optional topic mappings and interface info"""
        try:
            # Use broker port from interface_info if available
            mqtt_port = self.mqtt_port
            if interface_info and interface_info.get('broker_port'):
                mqtt_port = interface_info['broker_port']
            
            config_gen = DataBridgeConfigGenerator(mqtt_broker, mqtt_port)

            # Generate configurations with custom topic mappings and interface info
            mqtt_config = config_gen.generate_mqtt_consumer_config(submodels, topic_mappings, interface_info)
            aas_config = config_gen.generate_aas_server_config(
                submodels, self.basyx_config)
            
            # Generate JSONATA transformers based on AAS property types
            transformers_config = config_gen.generate_jsonata_transformers(submodels)
            
            # Generate routes configuration (with transformer references)
            routes_config = config_gen.generate_routes_config(submodels)

            # Use databridge directory in workspace root (parent of Registration_Service)
            script_dir = Path(__file__).resolve().parent.parent
            databridge_dir = script_dir.parent / 'databridge'
            databridge_dir.mkdir(exist_ok=True)

            # Save configurations
            self._save_json_config(
                databridge_dir / 'mqttconsumer.json', mqtt_config)
            self._save_json_config(
                databridge_dir / 'aasserver.json', aas_config)
            self._save_json_config(
                databridge_dir / 'jsonatatransformer.json', transformers_config)
            self._save_json_config(
                databridge_dir / 'routes.json', routes_config)

            logger.info("Generated databridge configurations")
            logger.info(f"Generated {len(transformers_config)} JSONATA transformers based on AAS types")
            if topic_mappings:
                logger.info(f"Applied {len(topic_mappings)} topic mappings from InterfaceMQTT")

        except Exception as e:
            logger.error(f"Failed to generate databridge configs: {e}")
            raise

    def _restart_databridge(self) -> bool:
        """Restart the databridge Docker container"""
        try:
            logger.info("Restarting databridge container...")
            
            # Check if docker command is available
            result = subprocess.run(['which', 'docker'], capture_output=True)
            if result.returncode != 0:
                logger.warning("Docker command not found. Skipping container restart.")
                logger.info("Please manually restart databridge: docker restart databridge")
                return False

            # Restart the container
            result = subprocess.run(
                ['docker', 'restart', 'databridge'],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                logger.info("✓ Databridge container restarted successfully")
                return True
            else:
                logger.warning(f"Failed to restart databridge: {result.stderr}")
                logger.info("Please manually restart databridge: docker restart databridge")
                return False

        except subprocess.TimeoutExpired:
            logger.warning("Timeout while restarting databridge container")
            return False
        except Exception as e:
            logger.warning(f"Could not restart databridge: {e}")
            logger.info("Please manually restart databridge: docker restart databridge")
            return False

    def _save_json_config(self, file_path: Path, config_data: Any):
        """Save configuration data as JSON file"""
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved configuration: {file_path}")

    def _make_request(self, method: str, url: str, data: Any = None) -> requests.Response:
        """Make HTTP request with error handling"""
        try:
            if method.upper() == 'GET':
                response = self.session.get(url)
            elif method.upper() == 'POST':
                response = self.session.post(url, json=data)
            elif method.upper() == 'PUT':
                response = self.session.put(url, json=data)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            # Don't raise for 409 (Conflict) as it means resource already exists
            if response.status_code not in [200, 201, 204, 409]:
                logger.warning(
                    f"HTTP {response.status_code} for {method} {url}: {response.text}")

            return response

        except Exception as e:
            logger.error(f"Request failed: {method} {url} - {e}")
            raise

    def list_registered_aas(self) -> Dict[str, Any]:
        """List all registered AAS and submodels"""
        try:
            # Get AAS shells from repository
            aas_response = self._make_request(
                'GET', self.basyx_config.aas_repo_url)
            aas_data = aas_response.json() if aas_response.status_code == 200 else {}
            aas_shells = aas_data.get('result', []) if isinstance(
                aas_data, dict) else []

            # Get submodels from repository
            sm_response = self._make_request(
                'GET', self.basyx_config.submodel_repo_url)
            sm_data = sm_response.json() if sm_response.status_code == 200 else {}
            submodels = sm_data.get('result', []) if isinstance(
                sm_data, dict) else []

            return {
                'aas_shells': aas_shells,
                'submodels': submodels
            }

        except Exception as e:
            logger.error(f"Failed to list registered AAS: {e}")
            return {'aas_shells': [], 'submodels': []}
    
    def list_shells(self) -> List[Dict[str, Any]]:
        """List all registered AAS shells (alias for compatibility)"""
        registered = self.list_registered_aas()
        return registered.get('aas_shells', [])
