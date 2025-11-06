"""
AAS Interface Parser

Extracts MQTT interface information from AAS InterfaceMQTT submodels
according to IDTA Asset Interfaces Description specification.
"""

import logging
from typing import Dict, List, Any, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class MQTTInterfaceParser:
    """Parser for IDTA Asset Interfaces Description - InterfaceMQTT submodel"""

    def __init__(self):
        self.interface_data = {}

    def parse_interface_submodels(self, submodels: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Parse all submodels looking for InterfaceMQTT and extract MQTT metadata
        
        Returns:
            Dict with structure:
            {
                'broker_url': str,
                'broker_host': str,
                'broker_port': int,
                'base_topic': str,
                'actions': {
                    'action_name': {
                        'request_topic': str,
                        'response_topic': str,
                        'additional_topics': [str],
                        'input_schema': str,
                        'output_schema': str,
                        'synchronous': bool,
                        'qos': int
                    }
                },
                'properties': {
                    'property_name': {
                        'topic': str,
                        'schema': str,
                        'direction': 'subscribe' | 'publish'
                    }
                }
            }
        """
        interface_info = {
            'broker_url': None,
            'broker_host': None,
            'broker_port': None,
            'base_topic': None,
            'actions': {},
            'properties': {}
        }

        for submodel in submodels:
            # Look for InterfaceMQTT submodel element collections
            elements = submodel.get('submodelElements', [])
            
            for element in elements:
                if element.get('idShort') == 'InterfaceMQTT' and element.get('modelType') == 'SubmodelElementCollection':
                    self._parse_interface_mqtt(element, interface_info)
        
        return interface_info

    def _parse_interface_mqtt(self, interface_element: Dict[str, Any], interface_info: Dict[str, Any]):
        """Parse InterfaceMQTT submodel element collection"""
        value = interface_element.get('value', [])
        
        for item in value:
            id_short = item.get('idShort', '')
            
            if id_short == 'EndpointMetadata':
                self._parse_endpoint_metadata(item, interface_info)
            elif id_short == 'InteractionMetadata':
                self._parse_interaction_metadata(item, interface_info)

    def _parse_endpoint_metadata(self, endpoint_element: Dict[str, Any], interface_info: Dict[str, Any]):
        """Parse EndpointMetadata to extract broker URL and base topic"""
        value = endpoint_element.get('value', [])
        
        for item in value:
            id_short = item.get('idShort', '')
            item_value = item.get('value', '')
            
            if id_short == 'base':
                # Parse MQTT URL: mqtt://host:port/base/topic
                interface_info['broker_url'] = item_value
                
                try:
                    parsed = urlparse(item_value)
                    interface_info['broker_host'] = parsed.hostname or 'localhost'
                    interface_info['broker_port'] = parsed.port or 1883
                    # Topic is everything after the domain
                    interface_info['base_topic'] = parsed.path.lstrip('/') if parsed.path else ''
                    
                    logger.info(f"Parsed MQTT endpoint: {interface_info['broker_host']}:{interface_info['broker_port']}, base: {interface_info['base_topic']}")
                except Exception as e:
                    logger.warning(f"Failed to parse MQTT URL '{item_value}': {e}")

    def _parse_interaction_metadata(self, interaction_element: Dict[str, Any], interface_info: Dict[str, Any]):
        """Parse InteractionMetadata to extract actions and properties"""
        value = interaction_element.get('value', [])
        
        for item in value:
            id_short = item.get('idShort', '')
            
            if id_short == 'actions':
                self._parse_actions(item, interface_info)
            elif id_short == 'properties':
                self._parse_properties(item, interface_info)

    def _parse_actions(self, actions_element: Dict[str, Any], interface_info: Dict[str, Any]):
        """Parse actions from InteractionMetadata"""
        actions = actions_element.get('value', [])
        
        for action in actions:
            action_name = action.get('idShort', '')
            if not action_name:
                continue
            
            action_data = {
                'request_topic': None,
                'response_topic': None,
                'additional_topics': [],
                'input_schema': None,
                'output_schema': None,
                'synchronous': False,
                'qos': 0,
                'retain': False
            }
            
            action_value = action.get('value', [])
            
            for item in action_value:
                id_short = item.get('idShort', '')
                item_value = item.get('value', '')
                
                if id_short == 'synchronous':
                    action_data['synchronous'] = str(item_value).lower() == 'true'
                elif id_short == 'input':
                    # File reference to input schema
                    action_data['input_schema'] = item_value
                elif id_short == 'output':
                    # File reference to output schema
                    action_data['output_schema'] = item_value
                elif id_short == 'forms':
                    self._parse_forms(item, action_data, interface_info)
            
            interface_info['actions'][action_name] = action_data
            logger.info(f"Parsed action '{action_name}': request={action_data['request_topic']}, response={action_data['response_topic']}")

    def _parse_forms(self, forms_element: Dict[str, Any], action_data: Dict[str, Any], interface_info: Dict[str, Any]):
        """Parse forms from action to extract request/response topics"""
        forms_value = forms_element.get('value', [])
        
        for item in forms_value:
            id_short = item.get('idShort', '')
            item_value = item.get('value', '')
            
            if id_short == 'href':
                # This is the request topic (relative path)
                base_topic = interface_info.get('base_topic', '')
                relative_topic = item_value.lstrip('/')
                action_data['request_topic'] = f"{base_topic}/{relative_topic}" if base_topic else relative_topic
                
            elif id_short == 'mqv_qos':
                action_data['qos'] = int(item_value) if item_value else 0
                
            elif id_short == 'mqv_retain':
                action_data['retain'] = str(item_value).lower() == 'true'
                
            elif id_short == 'response' and item.get('modelType') == 'SubmodelElementCollection':
                # Parse response topic
                response_value = item.get('value', [])
                for resp_item in response_value:
                    if resp_item.get('idShort') == 'href':
                        base_topic = interface_info.get('base_topic', '')
                        relative_topic = resp_item.get('value', '').lstrip('/')
                        action_data['response_topic'] = f"{base_topic}/{relative_topic}" if base_topic else relative_topic
                        
            elif id_short == 'additionalResponses' and item.get('modelType') == 'SubmodelElementCollection':
                # Parse additional response topics (e.g., data publications)
                additional_value = item.get('value', [])
                for add_item in additional_value:
                    if add_item.get('idShort') == 'href':
                        base_topic = interface_info.get('base_topic', '')
                        relative_topic = add_item.get('value', '').lstrip('/')
                        full_topic = f"{base_topic}/{relative_topic}" if base_topic else relative_topic
                        action_data['additional_topics'].append(full_topic)
                        logger.info(f"  Additional topic: {full_topic}")

    def _parse_properties(self, properties_element: Dict[str, Any], interface_info: Dict[str, Any]):
        """Parse properties from InteractionMetadata"""
        properties = properties_element.get('value', [])
        
        for prop in properties:
            prop_name = prop.get('idShort', '')
            if not prop_name:
                continue
            
            prop_data = {
                'topic': None,
                'schema': None,
                'schema_url': None,
                'direction': 'subscribe',  # Default
                'qos': 0
            }
            
            prop_value = prop.get('value', [])
            
            for item in prop_value:
                id_short = item.get('idShort', '')
                model_type = item.get('modelType', '')
                
                # Extract schema URL from File element
                if id_short == 'output' and model_type == 'File':
                    prop_data['schema_url'] = item.get('value', '')
                
                if id_short == 'forms':
                    forms_value = item.get('value', [])
                    for form_item in forms_value:
                        form_id = form_item.get('idShort', '')
                        form_val = form_item.get('value', '')
                        
                        if form_id == 'href':
                            base_topic = interface_info.get('base_topic', '')
                            relative_topic = form_val.lstrip('/')
                            prop_data['topic'] = f"{base_topic}/{relative_topic}" if base_topic else relative_topic
                            
                        elif form_id == 'mqv_controlPacket':
                            prop_data['direction'] = form_val
                            
                        elif form_id == 'mqv_qos':
                            prop_data['qos'] = int(form_val) if form_val else 0
            
            interface_info['properties'][prop_name] = prop_data
            logger.info(f"Parsed property '{prop_name}': topic={prop_data['topic']}, schema={prop_data['schema_url']}, direction={prop_data['direction']}")

    def extract_topic_mappings(self, submodels: List[Dict[str, Any]]) -> Dict[str, str]:
        """
        Extract topic mappings from InterfaceMQTT submodel
        
        Returns dict mapping MQTT topics to AAS property paths
        Format: {'mqtt/topic/path': 'SubmodelIdShort/PropertyIdShort'}
        """
        interface_info = self.parse_interface_submodels(submodels)
        topic_mappings = {}
        
        # Add action topics
        for action_name, action_data in interface_info.get('actions', {}).items():
            if action_data['request_topic']:
                # Map request topic to action (could map to properties if needed)
                topic_mappings[action_data['request_topic']] = f"Actions/{action_name}/Request"
                
            if action_data['response_topic']:
                topic_mappings[action_data['response_topic']] = f"Actions/{action_name}/Response"
                
            for add_topic in action_data.get('additional_topics', []):
                topic_mappings[add_topic] = f"Actions/{action_name}/AdditionalData"
        
        # Add property topics
        for prop_name, prop_data in interface_info.get('properties', {}).items():
            if prop_data['topic']:
                topic_mappings[prop_data['topic']] = f"Properties/{prop_name}"
        
        return topic_mappings
    
    def extract_interface_references(self, submodels: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """
        Extract InterfaceReference elements from Variables submodel and map them to InterfaceMQTT topics.
        
        Returns dict mapping Variable property paths to interface information:
        {
            'Variables/Weight.Value': {
                'topic': 'NN/Nybrovej/InnoLab/Filling/DATA/Weight',
                'interface_property': 'weight',
                'direction': 'publish'
            }
        }
        """
        # First parse InterfaceMQTT to get topic mappings
        interface_info = self.parse_interface_submodels(submodels)
        
        # Create lookup by interface property name
        interface_lookup = {}
        for prop_name, prop_data in interface_info.get('properties', {}).items():
            interface_lookup[prop_name] = prop_data
        
        # Now find all InterfaceReferences in other submodels (only for properties, not actions)
        variable_mappings = {}
        
        for submodel in submodels:
            submodel_short = submodel.get('idShort', '')
            
            # Skip InterfaceMQTT itself
            if 'Interface' in submodel_short:
                continue
            
            # Recursively find all InterfaceReference elements
            references = self._find_interface_references_recursive(
                submodel.get('submodelElements', []),
                submodel_short
            )
            
            for var_path, interface_ref in references:
                # Parse the reference to extract interface property name
                interface_property_name = self._extract_interface_property_from_ref(interface_ref)
                
                if interface_property_name and interface_property_name in interface_lookup:
                    interface_data = interface_lookup[interface_property_name]
                    # Convert path format from "Variables.Weight.Value" to "Variables/Weight.Value"
                    # Keep first dot as submodel separator, replace remaining dots with slashes
                    path_parts = var_path.split('.', 1)
                    if len(path_parts) == 2:
                        formatted_path = f"{path_parts[0]}/{path_parts[1]}"
                    else:
                        formatted_path = var_path
                    
                    variable_mappings[formatted_path] = {
                        'topic': interface_data['topic'],
                        'interface_property': interface_property_name,
                        'direction': interface_data.get('direction', 'subscribe'),
                        'qos': interface_data.get('qos', 0),
                        'schema': interface_data.get('schema'),
                        'schema_url': interface_data.get('schema_url')
                    }
                    logger.info(f"Mapped {formatted_path} → {interface_data['topic']} (schema: {interface_data.get('schema_url', 'none')})")
        
        return variable_mappings
    
    def _find_interface_references_recursive(self, elements: List[Dict[str, Any]], parent_path: str = "") -> List[tuple]:
        """
        Recursively find all ReferenceElement elements with InterfaceReference semanticId.
        
        Returns list of (property_path, reference_value) tuples.
        The property_path points to the parent Property that should receive data.
        """
        references = []
        
        for element in elements:
            id_short = element.get('idShort', '')
            model_type = element.get('modelType', '')
            current_path = f"{parent_path}.{id_short}" if parent_path else id_short
            
            if model_type == 'SubmodelElementCollection':
                # Check if this collection has an InterfaceReference child
                nested_elements = element.get('value', [])
                if isinstance(nested_elements, list):
                    # Look for Property and InterfaceReference siblings
                    # Note: We collect ALL properties, not just the first one, to handle cases
                    # like OccupationState where there's both a State property and a Queue list
                    # IMPORTANT: We skip SubmodelElementLists and SubmodelElementCollections as they
                    # cannot be updated with simple value writes
                    property_paths = []
                    interface_ref = None
                    
                    for child in nested_elements:
                        child_type = child.get('modelType', '')
                        child_id = child.get('idShort', '')
                        
                        if child_type == 'Property':
                            # This is a simple data property - add it to the list
                            property_paths.append(f"{current_path}.{child_id}")
                        elif child_type in ['SubmodelElementList', 'SubmodelElementCollection']:
                            # Skip lists and nested collections - they cannot be updated via DataBridge
                            logger.debug(f"Skipping {child_type} '{child_id}' - cannot update via simple value write")
                        elif child_type == 'ReferenceElement' and child_id == 'InterfaceReference':
                            # This is the interface reference
                            interface_ref = child.get('value', {})
                    
                    # If we found an InterfaceReference and at least one Property, map ALL properties
                    # This handles cases where a single MQTT message updates multiple properties
                    # (e.g., OccupationState with both State and potentially other fields)
                    if property_paths and interface_ref:
                        for prop_path in property_paths:
                            references.append((prop_path, interface_ref))
                    elif interface_ref and not property_paths:
                        logger.warning(f"Found InterfaceReference at '{current_path}' but no simple Properties to map (only lists/collections)")
                    
                    # Continue recursing into nested collections
                    references.extend(self._find_interface_references_recursive(nested_elements, current_path))
        
        return references
    
    def _extract_interface_property_from_ref(self, reference: Dict[str, Any]) -> Optional[str]:
        """
        Extract the interface property name from a ModelReference.
        
        Example reference:
        {
          "keys": [
            {"type": "Submodel", "value": "...AssetInterfacesDescription"},
            {"type": "SubmodelElementCollection", "value": "InterfaceMQTT"},
            {"type": "SubmodelElementCollection", "value": "InteractionMetadata"},
            {"type": "SubmodelElementCollection", "value": "properties"},
            {"type": "SubmodelElementCollection", "value": "weight"}  <-- This is what we want
          ]
        }
        
        Returns: "weight"
        """
        keys = reference.get('keys', [])
        if not keys:
            return None
        
        # The last key should be the property name
        last_key = keys[-1]
        return last_key.get('value')
