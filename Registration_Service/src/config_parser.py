"""
YAML Configuration Parser for AAS Registration

Parses YAML configuration files (like planarShuttle1.yaml) and extracts
information needed for:
1. Operation Delegation topics.json
2. DataBridge configuration
3. AAS generation
"""

import logging
from typing import Dict, List, Any, Optional, Tuple
from urllib.parse import urlparse
from pathlib import Path
import yaml

from .aas_generation.schema_handler import SchemaHandler

logger = logging.getLogger(__name__)


class ConfigParser:
    """
    Parser for AAS YAML configuration files.

    Extracts MQTT interface information, actions, properties, variables
    directly from YAML configs without needing to generate/parse full AAS.
    """

    def __init__(self, config_data: Dict[str, Any] = None, config_path: str = None):
        """
        Initialize with config data or path.

        Args:
            config_data: Parsed YAML config dictionary
            config_path: Path to YAML config file
        """
        if config_path:
            with open(config_path, 'r') as f:
                config_data = yaml.safe_load(f)

        if not config_data:
            raise ValueError(
                "Either config_data or config_path must be provided")

        # Config contains a single system with the system ID as the top-level key
        self.system_id = list(config_data.keys())[0]
        self.config = config_data[self.system_id]

        # Initialize schema handler for schema-driven field extraction
        self._schema_handler = SchemaHandler()

    @property
    def id_short(self) -> str:
        """Get the idShort of the asset"""
        return self.config.get('idShort', self.system_id)

    @property
    def aas_id(self) -> str:
        """Get the AAS ID"""
        return self.config.get('id', '')

    @property
    def global_asset_id(self) -> str:
        """Get the global asset ID"""
        return self.config.get('globalAssetId', '')

    def get_mqtt_endpoint(self) -> Dict[str, Any]:
        """
        Extract MQTT endpoint information from config.

        Returns:
            Dict with keys: broker_host, broker_port, base_topic
        """
        interface_config = self.config.get(
            'AssetInterfacesDescription', {}) or {}
        mqtt_config = interface_config.get('InterfaceMQTT', {}) or {}
        endpoint_config = mqtt_config.get('EndpointMetadata', {}) or {}

        result = {
            'broker_host': None,
            'broker_port': 1883,
            'base_topic': None,
            'broker_url': None
        }

        base_url = endpoint_config.get('base', '')
        if base_url:
            result['broker_url'] = base_url

            # Parse mqtt://host:port/base/topic
            if base_url.startswith('mqtt://'):
                base_url = base_url[7:]  # Remove mqtt://

            if '/' in base_url:
                host_port, base_topic = base_url.split('/', 1)
                result['base_topic'] = base_topic.rstrip('/')

                if ':' in host_port:
                    host, port = host_port.split(':', 1)
                    result['broker_host'] = host
                    result['broker_port'] = int(port)
                else:
                    result['broker_host'] = host_port
            else:
                result['broker_host'] = base_url

        return result

    def get_actions(self) -> List[Dict[str, Any]]:
        """
        Extract action definitions from config.

        Returns:
            List of action dictionaries with keys:
            - name: Action name
            - command_topic: Full MQTT command topic
            - response_topic: Full MQTT response topic
            - input_schema: Input schema URL
            - output_schema: Output schema URL
            - synchronous: Whether action is synchronous
        """
        interface_config = self.config.get(
            'AssetInterfacesDescription', {}) or {}
        mqtt_config = interface_config.get('InterfaceMQTT', {}) or {}
        interaction_metadata = mqtt_config.get('InteractionMetadata', {}) or {}
        actions_dict = interaction_metadata.get('actions', {}) or {}

        endpoint = self.get_mqtt_endpoint()
        base_topic = endpoint.get('base_topic', '')

        actions = []
        # Actions is a dict with action names as keys
        for action_name, action_config in actions_dict.items():
            forms = action_config.get('forms', {}) or {}
            response_forms = forms.get('response', {}) or {}

            # Build full topics
            cmd_href = forms.get('href', f'/CMD/{action_name}')
            resp_href = response_forms.get('href', f'/DATA/{action_name}')

            # Remove leading slash for joining
            cmd_suffix = cmd_href.lstrip('/')
            resp_suffix = resp_href.lstrip('/')

            command_topic = f"{base_topic}/{cmd_suffix}" if base_topic else cmd_suffix
            response_topic = f"{base_topic}/{resp_suffix}" if base_topic else resp_suffix

            actions.append({
                'name': action_name,
                'key': action_config.get('key', action_name),
                'title': action_config.get('title', action_name),
                'command_topic': command_topic,
                'response_topic': response_topic,
                'input_schema': action_config.get('input'),
                'output_schema': action_config.get('output'),
                'synchronous': str(action_config.get('synchronous', 'false')).lower() == 'true',
                'qos': int(forms.get('mqv_qos', 2)),
                'retain': str(forms.get('mqv_retain', 'false')).lower() == 'true'
            })

        return actions

    def get_properties(self) -> List[Dict[str, Any]]:
        """
        Extract property definitions from config.

        Returns:
            List of property dictionaries with keys:
            - name: Property name
            - topic: Full MQTT topic
            - schema: Schema URL
        """
        interface_config = self.config.get(
            'AssetInterfacesDescription', {}) or {}
        mqtt_config = interface_config.get('InterfaceMQTT', {}) or {}
        interaction_metadata = mqtt_config.get('InteractionMetadata', {}) or {}
        properties_dict = interaction_metadata.get('properties', {}) or {}

        endpoint = self.get_mqtt_endpoint()
        base_topic = endpoint.get('base_topic', '')

        properties = []
        # Properties is a dict with property names as keys
        for prop_name, prop_config in properties_dict.items():
            forms = prop_config.get('forms', {}) or {}

            # Build full topic
            href = forms.get('href', f'/DATA/{prop_name}')
            suffix = href.lstrip('/')
            topic = f"{base_topic}/{suffix}" if base_topic else suffix

            properties.append({
                'name': prop_name,
                'key': prop_config.get('key', prop_name),
                'title': prop_config.get('title', prop_name),
                'topic': topic,
                'schema': prop_config.get('output'),
                'qos': int(forms.get('mqv_qos', 0)),
                'retain': str(forms.get('mqv_retain', 'false')).lower() == 'true'
            })

        return properties

    def get_variables(self) -> List[Dict[str, Any]]:
        """
        Extract variable definitions from config.

        Returns:
            List of variable dictionaries with interface references
        """
        variables_dict = self.config.get('Variables', {}) or {}

        variables = []
        # Handle dict format: Variables: { VarName: {...}, ... }
        for var_name, var_config in variables_dict.items():
            variables.append({
                'name': var_name,
                'semantic_id': var_config.get('semanticId', ''),
                'interface_reference': var_config.get('InterfaceReference'),
                'values': {k: v for k, v in var_config.items()
                           if k not in ['semanticId', 'InterfaceReference']}
            })

        return variables

    def get_variables_with_schema_fields(self) -> List[Dict[str, Any]]:
        """
        Extract variable definitions with field names derived from MQTT schemas.

        This method resolves InterfaceReferences to their property schemas
        and uses the schema to determine the field names and types.
        The MQTT schema is the single source of truth for field definitions.

        Returns:
            List of variable dictionaries with schema-derived fields:
            - name: Variable name
            - semantic_id: Semantic ID for the variable
            - interface_reference: Name of the referenced interface property
            - fields: Dict of field_name -> {type, default_value, description}
        """
        variables = self.get_variables()
        properties = self.get_properties()

        # Build property lookup by name
        property_lookup = {p['name']: p for p in properties}

        enriched_variables = []
        for var in variables:
            interface_ref = var.get('interface_reference')

            # Start with config-defined values as defaults
            fields = var.get('values', {})

            # If there's an interface reference with a schema, derive fields from it
            if interface_ref and interface_ref in property_lookup:
                prop = property_lookup[interface_ref]
                schema_url = prop.get('schema')

                if schema_url:
                    # Get field definitions from schema
                    schema_fields = self._schema_handler.extract_data_fields(
                        schema_url)

                    # Use schema fields, with config values as overrides for defaults
                    fields = {}
                    for field_name, field_def in schema_fields.items():
                        fields[field_name] = {
                            'type': field_def['type'],
                            'aas_type': field_def['aas_type'],
                            'default_value': var.get('values', {}).get(
                                field_name, field_def['default_value']
                            ),
                            'description': field_def.get('description', '')
                        }

            enriched_variables.append({
                'name': var['name'],
                'semantic_id': var.get('semantic_id', ''),
                'interface_reference': interface_ref,
                'fields': fields
            })

        return enriched_variables

    def get_skills(self) -> Dict[str, Dict[str, Any]]:
        """
        Extract skill definitions from config.

        Returns:
            Dict mapping skill names to their configurations
        """
        return self.config.get('Skills', {}) or {}

    def get_capabilities(self) -> List[Dict[str, Any]]:
        """
        Extract capability definitions from config.

        Returns:
            List of capability dictionaries
        """
        capabilities_dict = self.config.get('Capabilities', {}) or {}

        capabilities = []
        # Handle dict format: Capabilities: { CapName: {...}, ... }
        for cap_name, cap_config in capabilities_dict.items():
            capabilities.append({
                'name': cap_name,
                'realized_by': cap_config.get('realizedBy')
            })

        return capabilities

    def get_operation_delegation_entry(self) -> Dict[str, Any]:
        """
        Generate topics.json entry for Operation Delegation Service.

        Returns:
            Dict in the format expected by topics.json
        """
        endpoint = self.get_mqtt_endpoint()
        actions = self.get_actions()

        skills = {}
        for action in actions:
            skills[action['name']] = {
                'command_topic': action['command_topic'],
                'response_topic': action['response_topic']
            }

        return {
            'base_topic': endpoint.get('base_topic', ''),
            'skills': skills
        }

    def get_databridge_property_mappings(self) -> List[Dict[str, Any]]:
        """
        Generate property mappings for DataBridge configuration.

        Links Variables to their InterfaceReference properties for
        MQTT -> AAS synchronization. Field names are derived from the
        MQTT schema - the single source of truth.

        Returns:
            List of mapping dictionaries with:
            - variable_name: Name of the variable in Variables submodel
            - property_name: Name of the interface property
            - mqtt_topic: Full MQTT topic for the property
            - schema: Schema URL for the property data
            - value_fields: List of field names derived from the MQTT schema
        """
        variables = self.get_variables()
        properties = self.get_properties()

        # Build property lookup by name
        property_lookup = {p['name']: p for p in properties}

        mappings = []
        for var in variables:
            interface_ref = var.get('interface_reference')
            if interface_ref and interface_ref in property_lookup:
                prop = property_lookup[interface_ref]
                schema_url = prop.get('schema')

                # Extract field names from the MQTT schema (single source of truth)
                if schema_url:
                    data_fields = self._schema_handler.extract_data_fields(
                        schema_url)
                    value_fields = list(data_fields.keys())
                else:
                    # Fallback: use fields defined in YAML config
                    value_fields = list(var.get('values', {}).keys())

                if value_fields:  # Only add mapping if there are fields to map
                    mappings.append({
                        'variable_name': var['name'],
                        'property_name': prop['name'],
                        'mqtt_topic': prop['topic'],
                        'schema': schema_url,
                        'value_fields': value_fields,
                        'qos': prop.get('qos', 0)
                    })

        return mappings


def parse_config_file(config_path: str) -> ConfigParser:
    """
    Convenience function to parse a YAML config file.

    Args:
        config_path: Path to YAML configuration file

    Returns:
        ConfigParser instance
    """
    return ConfigParser(config_path=config_path)


def parse_config_data(config_data: Dict[str, Any]) -> ConfigParser:
    """
    Convenience function to parse YAML config data.

    Args:
        config_data: Parsed YAML dictionary

    Returns:
        ConfigParser instance
    """
    return ConfigParser(config_data=config_data)
