#!/usr/bin/env python3
"""
Process AAS Generator Module

Generates Process AAS YAML configurations from capability matching results.
The generated AAS describes a production process instance with:
- Required capabilities matched to specific resources
- Process steps with their order and parameters
- Policy reference (behavior tree URL)
- Hierarchical relationships to product and resources
"""

import logging
import uuid
import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from .capability_matcher import MatchingResult, ProcessStep

logger = logging.getLogger(__name__)


@dataclass
class ProcessAASConfig:
    """Configuration for Process AAS generation"""
    base_url: str = "https://smartproductionlab.aau.dk"
    bt_base_url: str = "https://aausmartproductionlab.github.io/AP2030-UNS/BTDescriptions"
    asset_type_base: str = "https://smartproductionlab.aau.dk/Process/Production"
    location: str = "InnoLab, Nybrovej, AAU"


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
        matching_result: MatchingResult,
        product_aas_id: str,
        product_info: Dict[str, Any],
        requirements: Dict[str, Any],
        bt_filename: str = "production.xml"
    ) -> Dict[str, Any]:
        """
        Generate a complete Process AAS YAML configuration.
        
        Args:
            matching_result: Result from capability matching
            product_aas_id: AAS ID of the product
            product_info: Product information dictionary
            requirements: Extracted requirements from product
            bt_filename: Name of the behavior tree file
            
        Returns:
            Complete YAML configuration as dictionary
        """
        # Generate unique identifiers
        process_id = self._generate_process_id(product_info)
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
                    process_id, product_info, product_aas_id, timestamp
                ),
                
                # Required capabilities with resource references and embedded requirements
                'RequiredCapabilities': self._generate_required_capabilities(
                    matching_result, requirements
                ),
                
                # Policy reference (behavior tree)
                'Policy': {
                    'semantic_id': f"{self.config.base_url}/submodels/Policy/1/0",
                    'Policy': {
                        'semantic_id': 'https://www.behaviortree.dev/BehaviourTree'
                        'File': f"{self.config.bt_base_url}/{bt_filename}",
                        'contentType': 'application/xml',
                        'description': 'Production behavior tree policy'
                    }
                }
            }
        }
        
        return config
    
    def _generate_process_id(self, product_info: Dict[str, Any]) -> str:
        """Generate a unique process ID based on product info"""
        product_name = product_info.get('ProductInformation', {}).get('ProductName', 'Unknown')
        # Clean up product name for ID
        clean_name = ''.join(c for c in product_name if c.isalnum())[:20]
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
        product_info: Dict[str, Any],
        product_aas_id: str,
        timestamp: str
    ) -> Dict[str, Any]:
        """Generate process information section with product reference.
        
        Args:
            process_id: Unique process identifier
            product_info: Product information from AAS
            product_aas_id: AAS ID of the product (for ReferenceElement)
            timestamp: Creation timestamp
            
        Returns:
            ProcessInformation config dictionary
        """
        product_info_section = product_info.get('ProductInformation', {})
        
        return {
            'ProcessName': f"Production of {product_info_section.get('ProductName', 'Unknown')}",
            'ProcessType': 'AsepticFilling',
            'CreatedAt': timestamp,
            'Status': 'planned',
            'ProductReference': product_aas_id  # Will be converted to ReferenceElement
        }
    
    def _generate_required_capabilities(
        self, 
        matching_result: 'MatchingResult',
        requirements: Dict[str, Any]
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
            matching_result: Result from capability matching
            requirements: Requirements extracted from product (unused - kept for signature compatibility)
            
        Returns:
            Dictionary of capability types with their resource references
        """
        # Group capabilities by semantic type
        capability_groups: Dict[str, Dict[str, Any]] = {}
        
        # Add process step capabilities (stations)
        for match in matching_result.process_matches:
            step = match.process_step
            cap_name = step.name  # e.g., "Loading", "Dispensing"
            
            if cap_name not in capability_groups:
                capability_groups[cap_name] = {
                    'semantic_id': step.semantic_id,
                    'description': step.description,
                    'resources': {}
                }
            
            # Add resource AAS ID if matched
            if match.is_matched:
                primary = match.primary_resource
                resource_name = primary.resource_name
                # Use AAS ID directly - the builder will derive capability reference from it
                capability_groups[cap_name]['resources'][resource_name] = primary.aas_id
        
        # Add mover capabilities (planar shuttles) - grouped under MoveToPosition
        for mover in matching_result.movers:
            mover_caps = [
                cap for cap in matching_result.all_resources 
                if cap.aas_id == mover.aas_id
            ]
            for cap in mover_caps:
                cap_name = cap.name  # e.g., "MoveToPosition"
                
                if cap_name not in capability_groups:
                    capability_groups[cap_name] = {
                        'semantic_id': cap.semantic_id,
                        'description': 'Movement capability for product transport',
                        'resources': {}
                    }
                
                resource_name = cap.resource_name
                # Use AAS ID directly
                capability_groups[cap_name]['resources'][resource_name] = cap.aas_id
        
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
