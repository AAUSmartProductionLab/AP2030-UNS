#!/usr/bin/env python3
"""
Process AAS Generator Module

Generates Process AAS YAML configurations from planning capabilities.
The generated AAS describes a production process instance with:
- Required capabilities matched to specific resources
- Process steps with their order and parameters
- Policy reference (behavior tree URL)
- Hierarchical relationships to product and resources
"""

import logging
import uuid
import datetime
import os
import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ProcessAASConfig:
    """Configuration for Process AAS generation"""
    base_url: str = "https://smartproductionlab.aau.dk"
    bt_base_url: str = "https://aausmartproductionlab.github.io/AP2030-UNS/BTDescriptions"
    asset_type_base: str = "https://smartproductionlab.aau.dk/Process/Production"
    location: str = "InnoLab, Nybrovej, AAU"


@dataclass
class ProcessAASBundle:
    """Typed result for generated Process AAS artifacts."""

    process_aas_id: str
    system_id: str
    config: Dict[str, Any]
    yaml_content: str
    output_path: Optional[str] = None


class ProcessAASGenerator:
    """
    Generates Process AAS YAML configurations.
    
    Creates a complete AAS description for a production process instance,
    including capability bindings, process steps, and policy references.
    """
    
    def __init__(self, config: Optional[ProcessAASConfig] = None):
        """
        Initialize the Process AAS generator.
        
        Args:
            config: Generator configuration
        """
        self.config = config or ProcessAASConfig()
    
    def generate_config(
        self,
        planning_capabilities: List[Any],
        order_aas_id: str,
        order_info: Dict[str, Any],
        requirements: Dict[str, Any],
        bt_filename: str = "production.xml",
        planar_table_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate a complete Process AAS YAML configuration.
        
        Args:
            planning_capabilities: List of planner capabilities
            order_aas_id: AAS ID of the product
            order_info: Product information dictionary
            requirements: Extracted requirements from product
            bt_filename: Name of the behavior tree file
            planar_table_id: Optional AAS ID of the planar table (motion system)
            
        Returns:
            Complete YAML configuration as dictionary
        """
        # Generate unique identifiers
        process_id = self._generate_process_id(order_info)
        global_asset_id = self._generate_global_asset_id()
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        # Build the system ID (config key)
        system_id = f"{process_id}AAS"
        
        config = {
            system_id: {
                'idShort': system_id,
                'id': f"{self.config.base_url}/aas/{process_id}",
                'globalAssetId': global_asset_id,
                'derivedFrom': f"{self.config.base_url}/aas/templates/process",
                'assetType': f"{self.config.asset_type_base}/{process_id}",
                'serialNumber': f"PROC-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}",
                'location': self.config.location,
                
                # Process metadata with product reference
                'ProcessInformation': self._generate_process_info(
                    process_id, order_info, order_aas_id, timestamp
                ),
                
                # Required capabilities with resource references and embedded requirements
                'RequiredCapabilities': self._generate_required_capabilities(
                    planning_capabilities, requirements, planar_table_id
                ),
                
                # Policy reference (behavior tree)
                'Policy': {
                    'semantic_id': f"{self.config.base_url}/submodels/Policy/1/0",
                    'Policy': {
                        'semantic_id': 'https://www.behaviortree.dev/BehaviourTree',
                        'File': f"{self.config.bt_base_url}/{bt_filename}",
                        'contentType': 'application/xml',
                        'description': 'Production behavior tree policy'
                    }
                }
            }
        }
        
        return config

    def generate_process_aas_bundle(
        self,
        planning_capabilities: List[Any],
        order_aas_id: str,
        order_info: Dict[str, Any],
        requirements: Dict[str, Any],
        bt_filename: str = "production.xml",
        planar_table_id: Optional[str] = None,
        output_dir: Optional[str] = None,
    ) -> ProcessAASBundle:
        """Generate Process AAS config, IDs, YAML and optional persisted file path."""
        config = self.generate_config(
            planning_capabilities,
            order_aas_id,
            order_info,
            requirements,
            bt_filename,
            planar_table_id,
        )
        system_id = self.get_system_id(config)
        process_aas_id = self.get_aas_id(config)
        yaml_content = self.config_to_yaml(config)

        output_path = None
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            output_path = self.save_config(config, os.path.join(output_dir, f"{system_id}.yaml"))

        return ProcessAASBundle(
            process_aas_id=process_aas_id,
            system_id=system_id,
            config=config,
            yaml_content=yaml_content,
            output_path=output_path,
        )

    def build_registration_message(
        self,
        asset_id: str,
        yaml_content: str,
        request_prefix: str = "planner",
    ) -> Dict[str, Any]:
        """Build MQTT registration payload for the Registration Service."""
        import time

        return {
            "requestId": f"{request_prefix}-{asset_id}-{int(time.time())}",
            "assetId": asset_id,
            "configYaml": yaml_content,
        }

    def publish_registration_request(
        self,
        mqtt_client: Any,
        registration_topic: str,
        asset_id: str,
        yaml_content: str,
        qos: int = 2,
    ) -> Optional[Dict[str, Any]]:
        """Publish Process AAS registration request via MQTT."""
        if not mqtt_client:
            logger.warning("No MQTT client configured, skipping registration")
            return None

        message = self.build_registration_message(asset_id, yaml_content)
        mqtt_client.publish(
            registration_topic,
            json.dumps(message),
            qos=qos,
        )
        logger.info("Published registration request for %s to %s", asset_id, registration_topic)
        return message

    def publish_bundle_registration(
        self,
        mqtt_client: Any,
        registration_topic: str,
        bundle: ProcessAASBundle,
        qos: int = 2,
    ) -> Optional[Dict[str, Any]]:
        """Publish registration request from a generated ProcessAASBundle."""
        return self.publish_registration_request(
            mqtt_client,
            registration_topic,
            bundle.system_id,
            bundle.yaml_content,
            qos=qos,
        )
    
    def _generate_process_id(self, order_info: Dict[str, Any]) -> str:
        """Generate a unique process ID based on product info"""
        order_name = order_info.get('BatchInformation', {}).get('ProductName', 'Unknown')
        # Clean up product name for ID
        clean_name = ''.join(c for c in order_name if c.isalnum())[:20]
        timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
        return f"Process_{clean_name}_{timestamp}"
    
    def _generate_global_asset_id(self) -> str:
        """Generate a unique global asset ID"""
        import base64
        unique_id = str(uuid.uuid4())
        encoded = base64.urlsafe_b64encode(unique_id.encode()).decode().rstrip('=')
        return f"{self.config.base_url}/assets/{encoded}"
    
    def _generate_process_info(
        self,
        process_id: str,
        order_info: Dict[str, Any],
        order_aas_id: str,
        timestamp: str
    ) -> Dict[str, Any]:
        """Generate process information section with product reference.
        
        Args:
            process_id: Unique process identifier
            order_info: Product information from AAS
            order_aas_id: AAS ID of the product (for ReferenceElement)
            timestamp: Creation timestamp
            
        Returns:
            ProcessInformation config dictionary
        """
        order_name = order_info.get('BatchInformation', {}).get('ProductName', 'Unknown')
        
        return {
            'ProcessName': f"Production of {order_name}",
            'ProcessType': 'AsepticFilling',
            'CreatedAt': timestamp,
            'Status': 'planned',
            'ProductReference': order_aas_id  # Will be converted to ReferenceElement
        }
    
    def _generate_required_capabilities(
        self, 
        planning_capabilities: List[Any],
        requirements: Dict[str, Any],
        planar_table_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Generate required capabilities grouped by capability type.
        
        Capabilities are grouped by their semantic type (e.g., Loading, Dispensing, MoveToPosition).
        Each capability type contains:
        - semantic_id: The capability type's semantic ID
        - description: What this capability does in the process
        - resources: Dict of resource names to their globalAssetIds
        
        The registration service will resolve globalAssetIds to full capability references
        by querying BaSyx and using the standardized capability path structure.
        
        Args:
            planning_capabilities: Capabilities from AI planning pipeline
            requirements: Requirements extracted from product (unused - kept for signature compatibility)
            planar_table_id: Optional AAS ID of the planar table (motion system)
            
        Returns:
            Dictionary of capability types with their resource references
        """
        capability_groups: Dict[str, Dict[str, Any]] = {}

        for capability in planning_capabilities:
            cap_name = str(getattr(capability, 'name', '') or '').strip()
            if not cap_name:
                continue

            semantic_id = str(getattr(capability, 'semantic_id', '') or '').strip()
            if not semantic_id:
                semantic_id = f"https://smartproductionlab.aau.dk/Capability/{cap_name}"

            resources = dict(getattr(capability, 'resources', {}) or {})

            if cap_name not in capability_groups:
                capability_groups[cap_name] = {
                    'semantic_id': semantic_id,
                    'description': f"Planner-generated capability binding for {cap_name}",
                    'resources': {}
                }

            # Merge resources from all capability entries with same name.
            capability_groups[cap_name]['resources'].update(resources)
        
        # Add planar table (motion system) as a special resource
        # This is needed for the BT controller to prefetch interfaces for PackMLState checks
        if planar_table_id:
            capability_groups['PlanarTable'] = {
                'semantic_id': 'https://smartproductionlab.aau.dk/Capability/MotionSystem',
                'description': 'Planar motion system for shuttle coordination',
                'resources': {
                    'planarTableAAS': planar_table_id
                }
            }
        
        return capability_groups
    
    def config_to_yaml(self, config: Dict[str, Any]) -> str:
        """
        Convert configuration dictionary to YAML string.
        
        Args:
            config: Configuration dictionary
            
        Returns:
            YAML formatted string
        """
        import yaml
        
        # Custom representer for multiline strings
        def str_representer(dumper, data):
            if '\n' in data:
                return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
            return dumper.represent_scalar('tag:yaml.org,2002:str', data)
        
        yaml.add_representer(str, str_representer)
        
        return yaml.dump(
            config,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
            width=120
        )
    
    def save_config(self, config: Dict[str, Any], output_path: str) -> str:
        """
        Save configuration to a YAML file.
        
        Args:
            config: Configuration dictionary
            output_path: Path to save the file
            
        Returns:
            The file path
        """
        yaml_content = self.config_to_yaml(config)
        
        with open(output_path, 'w') as f:
            f.write(yaml_content)
        
        logger.info(f"Saved Process AAS config to {output_path}")
        return output_path
    
    def get_system_id(self, config: Dict[str, Any]) -> str:
        """Extract the system ID from a generated config"""
        return list(config.keys())[0]
    
    def get_aas_id(self, config: Dict[str, Any]) -> str:
        """Extract the AAS ID from a generated config"""
        system_id = self.get_system_id(config)
        return config[system_id].get('id', '')
