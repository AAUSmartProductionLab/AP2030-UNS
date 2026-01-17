"""
DataBridge Configuration Generator from YAML Configs

Generates BaSyx DataBridge configurations directly from YAML configuration
files without needing to parse AAS descriptions.

Key concepts:
- Reads InterfaceReferences and properties directly from YAML config
- Generates MQTT consumers, transformers, sinks, and routes
- Supports incremental updates (adds to existing configs)
"""

import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

from .config_parser import ConfigParser, parse_config_file
from .core.constants import DEFAULT_MQTT_BROKER, DEFAULT_MQTT_PORT, DEFAULT_BASYX_INTERNAL_URL, SemanticIds
from .utils import encode_aas_id, sanitize_id, topic_to_id

logger = logging.getLogger(__name__)


class DataBridgeFromConfig:
    """
    Generates BaSyx DataBridge configurations from YAML config files.

    Process:
    1. Parse YAML config to extract properties and variables
    2. Match InterfaceReferences to resolve MQTT topics
    3. Generate configs: consumers, transformers, sinks, routes
    """

    def __init__(self,
                 mqtt_broker: str = DEFAULT_MQTT_BROKER,
                 mqtt_port: int = DEFAULT_MQTT_PORT,
                 basyx_url: str = DEFAULT_BASYX_INTERNAL_URL):
        self.mqtt_broker = mqtt_broker
        self.mqtt_port = mqtt_port
        self.basyx_url = basyx_url

        # Configuration accumulators (for multi-asset generation)
        self.consumers: List[Dict] = []
        self.transformers: List[Dict] = []
        self.sinks: List[Dict] = []
        self.routes: List[Dict] = []

        # Track topics to avoid duplicates
        self._topic_ids: Dict[str, str] = {}

        # Track transformer metadata for JSONATA generation
        # Maps transformer_id -> {variable_name, field_name, mqtt_field}
        self._transformer_metadata: Dict[str, Dict] = {}

    def add_from_config(self, config: ConfigParser) -> Dict[str, int]:
        """
        Add DataBridge configurations from a parsed config.

        Args:
            config: Parsed ConfigParser instance

        Returns:
            Dict with counts of added configurations
        """
        system_id = config.system_id
        endpoint = config.get_mqtt_endpoint()
        mappings = config.get_databridge_property_mappings()

        # Note: We don't override broker from config endpoint since the generator
        # is initialized with the correct Docker-internal hostname (hivemq-broker).
        # The config files use external IPs which won't work inside Docker.

        counts = {'consumers': 0, 'transformers': 0, 'sinks': 0, 'routes': 0}

        # Group mappings by MQTT topic
        topic_groups: Dict[str, List[Dict]] = {}
        for mapping in mappings:
            topic = mapping['mqtt_topic']
            if topic not in topic_groups:
                topic_groups[topic] = []
            topic_groups[topic].append(mapping)

        # Generate configs for each topic group
        for topic, group_mappings in topic_groups.items():
            # Generate consumer for this topic
            consumer_id = self._generate_consumer(topic)
            if consumer_id:
                counts['consumers'] += 1

            # Collect all transformers, sinks, and their mappings for this topic
            all_transformers = []
            all_sinks = []
            datasink_mapping = {}

            for mapping in group_mappings:
                variable_name = mapping['variable_name']
                value_fields = mapping['value_fields']

                # Generate a separate transformer and sink for each value field
                for field in value_fields:
                    # Generate transformer for this specific field
                    # The field name IS the MQTT field name (harmonized naming)
                    transformer_id = self._generate_transformer(
                        system_id,
                        variable_name,
                        field
                    )
                    if transformer_id:
                        all_transformers.append(transformer_id)
                        counts['transformers'] += 1

                    # Generate sink for this specific field
                    sink_id = self._generate_sink(
                        system_id,
                        variable_name,
                        field
                    )
                    if sink_id:
                        all_sinks.append(sink_id)
                        counts['sinks'] += 1
                        # Map this sink to its transformer
                        datasink_mapping[sink_id] = [transformer_id]

            # Generate consolidated route for this topic
            if consumer_id and all_transformers and all_sinks:
                route_count = self._generate_route(
                    consumer_id, all_transformers, all_sinks, datasink_mapping
                )
                counts['routes'] += route_count

        logger.info(f"Added configs for {system_id}: {counts}")
        return counts

    def add_from_config_file(self, config_path: str) -> Dict[str, int]:
        """
        Add DataBridge configurations from a YAML config file.

        Args:
            config_path: Path to YAML config file

        Returns:
            Dict with counts of added configurations
        """
        config = parse_config_file(config_path)
        return self.add_from_config(config)

    def add_from_config_data(self, config_data: Dict[str, Any]) -> Dict[str, int]:
        """
        Add DataBridge configurations from YAML config data.

        Args:
            config_data: Parsed YAML dictionary

        Returns:
            Dict with counts of added configurations
        """
        config = ConfigParser(config_data=config_data)
        return self.add_from_config(config)

    def _generate_consumer(self, topic: str) -> Optional[str]:
        """
        Generate MQTT consumer configuration for a topic.

        Returns:
            Consumer unique ID, or None if already exists
        """
        # Create unique ID from topic
        consumer_id = topic_to_id(topic)

        # Check if already added
        if topic in self._topic_ids:
            return self._topic_ids[topic]

        self._topic_ids[topic] = consumer_id

        # Strip any existing tcp:// prefix to avoid duplication
        broker = self.mqtt_broker
        if broker.startswith('tcp://'):
            broker = broker[6:]

        self.consumers.append({
            "uniqueId": consumer_id,
            "serverUrl": broker,
            "serverPort": self.mqtt_port,
            "topic": topic
        })

        return consumer_id

    def _generate_transformer(self, system_id: str, variable_name: str,
                              field: str) -> Optional[str]:
        """
        Generate JSONATA transformer for a specific variable field.

        Args:
            system_id: The AAS system ID
            variable_name: The variable name (e.g., PackMLState, OccupationState)
            field: The specific field to transform - matches MQTT schema field name

        Returns:
            Transformer unique ID
        """
        # Create unique ID including the field
        transformer_id = f"{sanitize_id(system_id)}_{sanitize_id(variable_name)}_{sanitize_id(field)}_transformer"

        # Create JSONATA query file name
        query_file = f"{sanitize_id(system_id)}_{sanitize_id(variable_name)}_{sanitize_id(field)}.jsonata"

        self.transformers.append({
            "uniqueId": transformer_id,
            "queryLanguage": "JSONATA",
            "queryPath": f"queries/{query_file}",
            "inputType": "JsonString",
            "outputType": "JsonString"
        })

        # Store metadata for JSONATA query generation
        # Since field names are now harmonized, field == mqtt_field
        self._transformer_metadata[transformer_id] = {
            'variable_name': variable_name,
            'field': field
        }

        return transformer_id

    def _generate_sink(self, system_id: str, variable_name: str,
                       field: str) -> Optional[str]:
        """
        Generate AAS server sink for a specific variable field.

        Args:
            system_id: The AAS system ID
            variable_name: The variable name (e.g., PackMLState, OccupationState)
            field: The specific field (e.g., Value, State, Queue)

        Returns:
            Sink unique ID
        """
        # Create unique ID including the field
        sink_id = f"{sanitize_id(system_id)}_{sanitize_id(variable_name)}_sink_{sanitize_id(field)}"

        # Build the submodel element path
        submodel_id = f"https://smartproductionlab.aau.dk/submodels/instances/{system_id}/Variables"
        id_short_path = f"{variable_name}.{field}"

        encoded_sm_id = encode_aas_id(submodel_id)

        self.sinks.append({
            "uniqueId": sink_id,
            "submodelEndpoint": f"{self.basyx_url}/submodels/{encoded_sm_id}",
            "idShortPath": id_short_path,
            "api": "DotAasV3"
        })

        return sink_id

    def _generate_route(self, consumer_id: str, transformers: List[str],
                        sinks: List[str], datasink_mapping: Dict[str, List[str]]) -> int:
        """
        Generate a single consolidated route connecting consumer to all transformers and sinks.

        Args:
            consumer_id: The MQTT consumer ID
            transformers: List of transformer IDs
            sinks: List of sink IDs
            datasink_mapping: Mapping of sink_id -> [transformer_ids]

        Returns:
            Number of routes generated (always 1)
        """
        if not sinks:
            return 0

        route = {
            "datasource": consumer_id,
            "transformers": transformers,
            "datasinks": sinks,
            "trigger": "event"
        }

        # Only add datasinkMappingConfiguration if there are multiple sinks
        if len(sinks) > 1:
            route["datasinkMappingConfiguration"] = datasink_mapping

        self.routes.append(route)
        return 1

    def save_configs(self, output_dir: str) -> Dict[str, int]:
        """
        Save all generated configurations to files.

        Args:
            output_dir: Directory to write config files

        Returns:
            Dict with counts of saved configurations
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        queries_path = output_path / 'queries'
        queries_path.mkdir(exist_ok=True)

        # Save main config files
        self._write_json(output_path / 'mqttconsumer.json', self.consumers)
        self._write_json(
            output_path / 'jsonatatransformer.json', self.transformers)
        self._write_json(output_path / 'aasserver.json', self.sinks)
        self._write_json(output_path / 'routes.json', self.routes)

        # Generate JSONATA query files
        for transformer in self.transformers:
            query_file = transformer.get(
                'queryPath', '').replace('queries/', '')
            if query_file:
                query_content = self._generate_jsonata_query(
                    transformer['uniqueId'])
                with open(queries_path / query_file, 'w') as f:
                    f.write(query_content)

        return {
            'consumers': len(self.consumers),
            'transformers': len(self.transformers),
            'sinks': len(self.sinks),
            'routes': len(self.routes)
        }

    def _generate_jsonata_query(self, transformer_id: str) -> str:
        """
        Generate JSONATA query content for a transformer.

        The query extracts values from MQTT JSON and formats for AAS.
        Since field names are harmonized between YAML configs and MQTT schemas,
        we simply extract $.{field_name} from the MQTT message.
        """
        metadata = self._transformer_metadata.get(transformer_id, {})
        field = metadata.get('field', '')

        if not field:
            return '$'

        # Simple, direct field extraction - field names match MQTT schema
        # Use $string() wrapper to ensure proper string formatting for AAS
        return f'$string($.{field})'

    def _write_json(self, path: Path, data: Any):
        """Write JSON data to file"""
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
        logger.info(f"Saved {path}")

    def clear(self):
        """Clear all accumulated configurations"""
        self.consumers = []
        self.transformers = []
        self.sinks = []
        self.routes = []
        self._topic_ids = {}
        self._transformer_metadata = {}


def generate_databridge_from_configs(config_paths: List[str],
                                     output_dir: str,
                                     mqtt_broker: str = DEFAULT_MQTT_BROKER,
                                     mqtt_port: int = DEFAULT_MQTT_PORT,
                                     basyx_url: str = DEFAULT_BASYX_INTERNAL_URL) -> Dict[str, int]:
    """
    Generate DataBridge configurations from multiple YAML config files.

    Args:
        config_paths: List of paths to YAML config files
        output_dir: Output directory for config files
        mqtt_broker: MQTT broker hostname
        mqtt_port: MQTT broker port
        basyx_url: BaSyx AAS environment URL

    Returns:
        Dict with total counts of generated configurations
    """
    generator = DataBridgeFromConfig(mqtt_broker, mqtt_port, basyx_url)

    total_counts = {'consumers': 0, 'transformers': 0, 'sinks': 0, 'routes': 0}

    for config_path in config_paths:
        try:
            counts = generator.add_from_config_file(config_path)
            for key in total_counts:
                total_counts[key] += counts.get(key, 0)
        except Exception as e:
            logger.error(f"Failed to process {config_path}: {e}")

    generator.save_configs(output_dir)

    return total_counts


def generate_databridge_from_directory(config_dir: str,
                                       output_dir: str,
                                       mqtt_broker: str = DEFAULT_MQTT_BROKER,
                                       mqtt_port: int = DEFAULT_MQTT_PORT,
                                       basyx_url: str = DEFAULT_BASYX_INTERNAL_URL) -> Dict[str, int]:
    """
    Generate DataBridge configurations from all YAML files in a directory.

    Args:
        config_dir: Directory containing YAML config files
        output_dir: Output directory for config files
        mqtt_broker: MQTT broker hostname
        mqtt_port: MQTT broker port
        basyx_url: BaSyx AAS environment URL

    Returns:
        Dict with total counts of generated configurations
    """
    config_dir = Path(config_dir)
    if not config_dir.exists():
        logger.error(f"Config directory not found: {config_dir}")
        return {}

    config_paths = list(config_dir.glob('*.yaml')) + \
        list(config_dir.glob('*.yml'))

    if not config_paths:
        logger.warning(f"No YAML files found in {config_dir}")
        return {}

    return generate_databridge_from_configs(
        [str(p) for p in config_paths],
        output_dir,
        mqtt_broker,
        mqtt_port,
        basyx_url
    )
