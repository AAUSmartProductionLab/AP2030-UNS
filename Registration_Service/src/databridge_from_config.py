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
import re
import requests
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

from .config_parser import ConfigParser, parse_config_file

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
                 mqtt_broker: str = "192.168.0.104", 
                 mqtt_port: int = 1883,
                 basyx_url: str = "http://aas-env:8081"):
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
        
        # Override broker if specified in config
        if endpoint.get('broker_host'):
            self.mqtt_broker = endpoint['broker_host']
        if endpoint.get('broker_port'):
            self.mqtt_port = endpoint['broker_port']
        
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
            
            # Generate transformers and sinks for each variable mapping
            transformer_ids = []
            sink_ids = []
            
            for mapping in group_mappings:
                # Generate transformer
                transformer_id = self._generate_transformer(
                    system_id, 
                    mapping['variable_name'],
                    mapping['value_fields']
                )
                if transformer_id:
                    transformer_ids.append(transformer_id)
                    counts['transformers'] += 1
                
                # Generate sink
                sink_id = self._generate_sink(
                    system_id,
                    mapping['variable_name'],
                    mapping['value_fields']
                )
                if sink_id:
                    sink_ids.append(sink_id)
                    counts['sinks'] += 1
            
            # Generate route connecting consumer to transformers and sinks
            if consumer_id and transformer_ids and sink_ids:
                route_count = self._generate_routes(consumer_id, transformer_ids, sink_ids)
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
        consumer_id = self._topic_to_id(topic)
        
        # Check if already added
        if topic in self._topic_ids:
            return self._topic_ids[topic]
        
        self._topic_ids[topic] = consumer_id
        
        self.consumers.append({
            "uniqueId": consumer_id,
            "serverUrl": f"tcp://{self.mqtt_broker}:{self.mqtt_port}",
            "topic": topic
        })
        
        return consumer_id
    
    def _generate_transformer(self, system_id: str, variable_name: str, 
                              value_fields: List[str]) -> Optional[str]:
        """
        Generate JSONATA transformer for a variable.
        
        Returns:
            Transformer unique ID
        """
        # Create unique ID
        transformer_id = f"{self._sanitize_id(system_id)}_{self._sanitize_id(variable_name)}_transformer"
        
        # Create JSONATA query file name
        query_file = f"{self._sanitize_id(system_id)}_{self._sanitize_id(variable_name)}.jsonata"
        
        self.transformers.append({
            "uniqueId": transformer_id,
            "queryPath": f"queries/{query_file}",
            "inputType": "JsonString",
            "outputType": "JsonString"
        })
        
        return transformer_id
    
    def _generate_sink(self, system_id: str, variable_name: str,
                       value_fields: List[str]) -> Optional[str]:
        """
        Generate AAS server sink for a variable.
        
        Returns:
            Sink unique ID
        """
        # Create unique ID  
        sink_id = f"{self._sanitize_id(system_id)}_{self._sanitize_id(variable_name)}_sink"
        
        # Build the submodel element path
        # Variables submodel, variable collection, specific property
        submodel_id = f"https://smartproductionlab.aau.dk/submodels/instances/{system_id}/Variables"
        
        # For each value field, we need a separate sink entry
        for field in value_fields:
            field_sink_id = f"{sink_id}_{self._sanitize_id(field)}"
            id_short_path = f"{variable_name}.{field}"
            
            import base64
            encoded_sm_id = base64.b64encode(submodel_id.encode()).decode()
            
            self.sinks.append({
                "uniqueId": field_sink_id,
                "submodelEndpoint": f"{self.basyx_url}/submodels/{encoded_sm_id}",
                "idShortPath": id_short_path
            })
        
        return sink_id
    
    def _generate_routes(self, consumer_id: str, transformer_ids: List[str], 
                         sink_ids: List[str]) -> int:
        """
        Generate routes connecting consumer to transformers and sinks.
        
        Returns:
            Number of routes generated
        """
        count = 0
        
        # Each transformer should map to corresponding sink(s)
        for i, transformer_id in enumerate(transformer_ids):
            # Get base sink ID (without field suffix)
            base_sink_id = sink_ids[i] if i < len(sink_ids) else sink_ids[-1]
            
            # Find all sinks that match this base
            matching_sinks = [s['uniqueId'] for s in self.sinks 
                            if s['uniqueId'].startswith(base_sink_id)]
            
            for sink_id in matching_sinks:
                route_id = f"route_{consumer_id}_to_{sink_id}"
                
                self.routes.append({
                    "routeId": route_id,
                    "datasource": consumer_id,
                    "transformers": [transformer_id],
                    "datasinks": [sink_id]
                })
                count += 1
        
        return count
    
    def _topic_to_id(self, topic: str) -> str:
        """Convert MQTT topic to a valid unique ID"""
        # Replace / with _ and remove special chars
        return re.sub(r'[^a-zA-Z0-9_]', '_', topic)
    
    def _sanitize_id(self, name: str) -> str:
        """Sanitize a name for use as an ID"""
        return re.sub(r'[^a-zA-Z0-9_]', '_', name)
    
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
        self._write_json(output_path / 'jsonatatransformer.json', self.transformers)
        self._write_json(output_path / 'aasserver.json', self.sinks)
        self._write_json(output_path / 'routes.json', self.routes)
        
        # Generate JSONATA query files
        for transformer in self.transformers:
            query_file = transformer.get('queryPath', '').replace('queries/', '')
            if query_file:
                query_content = self._generate_jsonata_query(transformer['uniqueId'])
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
        """
        # Default passthrough query - can be customized based on schema
        return "$.value"
    
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


def generate_databridge_from_configs(config_paths: List[str], 
                                     output_dir: str,
                                     mqtt_broker: str = "192.168.0.104",
                                     mqtt_port: int = 1883,
                                     basyx_url: str = "http://aas-env:8081") -> Dict[str, int]:
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
                                        mqtt_broker: str = "192.168.0.104",
                                        mqtt_port: int = 1883,
                                        basyx_url: str = "http://aas-env:8081") -> Dict[str, int]:
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
    
    config_paths = list(config_dir.glob('*.yaml')) + list(config_dir.glob('*.yml'))
    
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
