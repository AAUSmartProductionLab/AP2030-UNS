"""
BaSyx Registration Service

Handles registration of AAS shells, submodels, and concept descriptions
with BaSyx server and registries using the official BaSyx Python SDK.
"""

import base64
import copy
import logging
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Optional
import requests

from basyx.aas import model
from basyx.aas.adapter import json as aas_json

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

    def _to_dict(self, obj: Any) -> Dict[str, Any]:
        """Convert SDK object to dict if needed"""
        if isinstance(obj, dict):
            return copy.deepcopy(obj)
        elif hasattr(obj, 'id') or hasattr(obj, 'id_short'):  # SDK object
            import json
            obj_json = json.dumps(obj, cls=aas_json.AASToJsonEncoder)
            return json.loads(obj_json)
        return obj

    def register_aasx(self, aasx_path: str) -> bool:
        """Register AASX file and configure databridge."""
        try:
            logger.info(f"Starting registration of {aasx_path}")
            parser = AASXParser(aasx_path)
            object_store = parser.parse()
            
            shells = parser.get_shells(object_store)
            submodels = parser.get_submodels(object_store)
            concept_descriptions = parser.get_concept_descriptions(object_store)

            logger.info(f"Found {len(shells)} AAS shell(s), "
                       f"{len(submodels)} submodel(s), "
                       f"{len(concept_descriptions)} concept description(s)")

            for cd in concept_descriptions:
                self.register_concept_description(cd)

            for submodel in submodels:
                self._register_submodel(submodel)

            for shell in shells:
                self._register_aas_shell_with_submodels(shell, submodels)

            self.generate_databridge_configs(submodels, self.mqtt_broker)

            logger.info("Registration completed successfully!")
            return True

        except Exception as e:
            logger.error(f"Registration failed: {e}", exc_info=True)
            return False

    def register_from_json(self, 
                          json_path: Optional[str] = None,
                          submodels: Optional[List[Any]] = None,
                          shells: Optional[List[Any]] = None,
                          concept_descriptions: Optional[List[Any]] = None) -> bool:
        """
        Register AAS from JSON file or direct lists of objects/dicts.
        
        Args:
            json_path: Path to JSON file (optional)
            submodels: List of submodels (optional)
            shells: List of AAS shells (optional)
            concept_descriptions: List of concept descriptions (optional)
        """
        try:
            if json_path:
                logger.info(f"Starting registration from JSON: {json_path}")
                # Use standard JSON parser if checking for SDK objects, 
                # but if we want to support both SDK and pure dicts, we might need custom logic.
                # Here we assume json_path points to an environment serialization.
                object_store = aas_json.read_aas_json_file(json_path, failsafe=True)
                
                shells = [obj for obj in object_store if isinstance(obj, model.AssetAdministrationShell)]
                submodels = [obj for obj in object_store if isinstance(obj, model.Submodel)]
                concept_descriptions = [obj for obj in object_store if isinstance(obj, model.ConceptDescription)]
            
            # Ensure lists are not None
            shells = shells or []
            submodels = submodels or []
            concept_descriptions = concept_descriptions or []

            logger.info(f"Found {len(shells)} AAS shell(s), "
                       f"{len(submodels)} submodel(s), "
                       f"{len(concept_descriptions)} concept description(s)")

            # Parse InterfaceMQTT
            interface_parser = MQTTInterfaceParser()
            # Parser handles SDK objects or dicts now
            interface_info = interface_parser.parse_interface_submodels(submodels)
            interface_references = interface_parser.extract_interface_references(submodels)
            
            if interface_info.get('broker_host'):
                logger.info(f"Using MQTT broker from InterfaceMQTT: "
                          f"{interface_info['broker_host']}:{interface_info['broker_port']}")
                self.mqtt_broker = interface_info['broker_host']
                self.mqtt_port = interface_info['broker_port']
            
            if interface_references:
                logger.info(f"Extracted {len(interface_references)} InterfaceReference mappings")

            for cd in concept_descriptions:
                self.register_concept_description(cd)

            for submodel in submodels:
                self._register_submodel(submodel)

            for shell in shells:
                if shell:
                    self._register_aas_shell_with_submodels(shell, submodels)

            self.generate_databridge_configs(submodels, self.mqtt_broker, interface_info, interface_references)

            self._restart_databridge()
            logger.info("Registration completed successfully!")
            return True

        except Exception as e:
            logger.error(f"Registration failed: {e}", exc_info=True)
            return False

    def _register_aas_shell_with_submodels(self, shell: Any, submodels: List[Any]) -> bool:
        """Register AAS shell with BaSyx server."""
        try:
            shell_repo_data = self._to_dict(shell)
            if not shell_repo_data:
                return False

            if 'modelType' not in shell_repo_data:
                shell_repo_data['modelType'] = 'AssetAdministrationShell'

            encoded_id = base64.b64encode(shell_repo_data['id'].encode()).decode()
            self._make_request('POST', self.basyx_config.aas_repo_url, shell_repo_data)

            logger.info(f"Registered AAS shell: {shell_repo_data['idShort']}")
            
            # Convert submodels to list of dicts for descriptor registration
            submodel_dicts = [self._to_dict(sm) for sm in submodels]
            self._register_shell_descriptor(shell_repo_data, encoded_id, submodel_dicts)

            return True

        except Exception as e:
            logger.error(f"Failed to register AAS shell: {e}", exc_info=True)
            return False

    def _register_submodel(self, submodel: Any) -> bool:
        """Register submodel with BaSyx server."""
        try:
            submodel_repo_data = self._to_dict(submodel)
            if not submodel_repo_data:
                return False

            if 'modelType' not in submodel_repo_data:
                submodel_repo_data['modelType'] = 'Submodel'
            
            submodel_repo_data = self._preprocess_submodel_for_registration(submodel_repo_data)
            encoded_id = base64.b64encode(submodel_repo_data['id'].encode()).decode()
            
            self._make_request('POST', self.basyx_config.submodel_repo_url, submodel_repo_data)

            logger.info(f"Registered submodel: {submodel_repo_data['idShort']}")
            
            self._upload_file_attachments(submodel_repo_data, encoded_id)
            self._register_submodel_descriptor(submodel_repo_data, encoded_id)

            return True

        except Exception as e:
            logger.error(f"Failed to register submodel: {e}", exc_info=True)
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
            
            # Skip if value is a URL (already converted to GitHub Pages or other URL)
            if file_value.startswith('http://') or file_value.startswith('https://'):
                logger.debug(f"Skipping upload for URL reference: {file_value}")
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

    def register_concept_description(self, cd: Any) -> bool:
        """Register a concept description (SDK object or dict)."""
        try:
            cd_data = self._to_dict(cd)
            if not cd_data:
                return False

            if 'modelType' not in cd_data:
                cd_data['modelType'] = 'ConceptDescription'
            
            cd_url = f"{self.basyx_config.base_url}/concept-descriptions"
            response = self._make_request('POST', cd_url, cd_data)
            
            if response.status_code in [200, 201, 409]:
                logger.info(f"Registered concept description: {cd_data.get('idShort', 'unknown')}")
                return True
            else:
                logger.debug(f"Concept description registration status: {response.status_code}")
                return False
                
        except Exception as e:
            logger.debug(f"Failed to register concept description: {e}")
            return False

    def generate_databridge_configs(
        self,
        submodels: List[Any],
        mqtt_broker: str,
        interface_info: Optional[Dict[str, Any]] = None,
        interface_references: Optional[Dict[str, Dict[str, Any]]] = None
    ):
        """Generate and save databridge configuration files."""
        try:
            # Convert SDK submodels to dicts if needed
            submodels_dicts = [self._to_dict(sm) for sm in submodels]
            
            mqtt_port = self.mqtt_port
            if interface_info and interface_info.get('broker_port'):
                mqtt_port = interface_info['broker_port']
            
            config_gen = DataBridgeConfigGenerator(mqtt_broker, mqtt_port)

            script_dir = Path(__file__).resolve().parent.parent
            databridge_dir = script_dir.parent / 'databridge'
            databridge_dir.mkdir(exist_ok=True)

            port = 8081
            if ':' in self.basyx_config.base_url:
                port = int(self.basyx_config.base_url.rsplit(':', 1)[1].rstrip('/'))
            
            counts = config_gen.generate_all_configs(
                submodels=submodels_dicts,
                output_dir=str(databridge_dir),
                basyx_url=f"http://aas-env:{port}"
            )

            logger.info("✓ Generated databridge configurations")
            logger.info(f"  - {counts['consumers']} MQTT consumers")
            logger.info(f"  - {counts['sinks']} AAS server endpoints")
            logger.info(f"  - {counts['transformers']} JSONATA transformers")
            logger.info(f"  - {counts['routes']} routes")

        except Exception as e:
            logger.error(f"Failed to generate databridge configs: {e}", exc_info=True)
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
