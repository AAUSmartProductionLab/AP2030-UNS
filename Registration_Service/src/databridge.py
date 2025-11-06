"""
BaSyx DataBridge Configuration Generator - Rebuilt from scratch

Generates complete DataBridge configurations by analyzing InterfaceReferences
in the Variables submodel that point to properties in AssetInterfacesDescription.

Key concepts:
- InterfaceReference: Links Variables properties to MQTT topics via AssetInterfacesDescription
- Routes: One datasource (MQTT topic) can feed multiple datasinks (AAS properties) via transformers
- JSONATA: Transformers extract and convert data from MQTT JSON to AAS property values
"""

import base64
import json
import logging
import os
import requests
from typing import Dict, List, Any, Optional, Tuple

logger = logging.getLogger(__name__)


class DataBridgeConfigGenerator:
    """
    Generates BaSyx DataBridge configurations from AAS with InterfaceReferences.
    
    Process:
    1. Parse InterfaceReferences from Variables submodel
    2. Resolve references to AssetInterfacesDescription properties
    3. Extract MQTT topics and schemas from InterfaceMQTT
    4. Group properties by MQTT topic (multiple properties can share one topic)
    5. Generate configs: consumers, transformers, sinks, routes
    """

    def __init__(self, mqtt_broker: str = "192.168.0.104", mqtt_port: int = 1883):
        self.mqtt_broker = mqtt_broker
        self.mqtt_port = mqtt_port

    def generate_all_configs(self, submodels: List[Dict[str, Any]], 
                            output_dir: str,
                            basyx_url: str = "http://aas-env:8081") -> Dict[str, int]:
        """
        Generate all DataBridge configuration files from submodels.
        
        Args:
            submodels: List of AAS submodels
            output_dir: Directory to write config files
            basyx_url: Base URL for AAS environment
            
        Returns:
            Dictionary with counts of generated configs
        """
        # Step 1: Find Variables and AssetInterfacesDescription submodels
        variables_sm = None
        interfaces_sm = None
        
        for sm in submodels:
            id_short = sm.get('idShort', '')
            if id_short == 'Variables':
                variables_sm = sm
            elif id_short == 'AssetInterfacesDescription':
                interfaces_sm = sm
        
        if not variables_sm:
            raise ValueError("Variables submodel not found")
        if not interfaces_sm:
            raise ValueError("AssetInterfacesDescription submodel not found")
        
        logger.info(f"Found Variables submodel: {variables_sm.get('id')}")
        logger.info(f"Found AssetInterfacesDescription submodel: {interfaces_sm.get('id')}")
        
        # Step 2: Extract InterfaceMQTT endpoint and property definitions
        mqtt_endpoint, mqtt_properties = self._parse_interface_mqtt(interfaces_sm)
        logger.info(f"MQTT Endpoint: {mqtt_endpoint}")
        logger.info(f"Found {len(mqtt_properties)} property definitions in InterfaceMQTT")
        
        # Step 3: Parse InterfaceReferences from Variables
        interface_refs = self._parse_interface_references(variables_sm, interfaces_sm, mqtt_properties)
        logger.info(f"Resolved {len(interface_refs)} InterfaceReferences")
        
        # Step 4: Group by MQTT topic (multiple properties can share one topic)
        topic_groups = self._group_by_topic(interface_refs)
        logger.info(f"Grouped into {len(topic_groups)} unique MQTT topics")
        
        # Step 5: Generate configurations
        os.makedirs(output_dir, exist_ok=True)
        queries_dir = os.path.join(output_dir, 'queries')
        os.makedirs(queries_dir, exist_ok=True)
        
        consumers = self._generate_consumers(topic_groups, mqtt_endpoint)
        transformers = self._generate_transformers(interface_refs, queries_dir)
        sinks = self._generate_sinks(interface_refs, variables_sm, basyx_url)
        routes = self._generate_routes(topic_groups, interface_refs)
        
        # Write configuration files
        self._write_json(os.path.join(output_dir, 'mqttconsumer.json'), consumers)
        self._write_json(os.path.join(output_dir, 'jsonatatransformer.json'), transformers)
        self._write_json(os.path.join(output_dir, 'aasserver.json'), sinks)
        self._write_json(os.path.join(output_dir, 'routes.json'), routes)
        
        return {
            'consumers': len(consumers),
            'transformers': len(transformers),
            'sinks': len(sinks),
            'routes': len(routes)
        }
    
    def _parse_interface_mqtt(self, interfaces_sm: Dict[str, Any]) -> Tuple[Dict[str, str], Dict[str, Dict]]:
        """
        Parse InterfaceMQTT to extract endpoint and property definitions.
        
        Returns:
            (mqtt_endpoint_info, property_definitions_dict)
        """
        endpoint_info = {}
        properties = {}
        
        # Find InterfaceMQTT collection
        for elem in interfaces_sm.get('submodelElements', []):
            if elem.get('idShort') == 'InterfaceMQTT':
                # Extract endpoint metadata
                for item in elem.get('value', []):
                    if item.get('idShort') == 'EndpointMetadata':
                        for meta in item.get('value', []):
                            if meta.get('idShort') == 'base':
                                base = meta.get('value', '')
                                # Parse mqtt://host:port/baseTopic
                                if base.startswith('mqtt://'):
                                    base = base[7:]  # Remove mqtt://
                                    if '/' in base:
                                        host_port, base_topic = base.split('/', 1)
                                        endpoint_info['base_topic'] = base_topic
                                        if ':' in host_port:
                                            host, port = host_port.split(':', 1)
                                            endpoint_info['host'] = host
                                            endpoint_info['port'] = int(port)
                    
                    # Extract property definitions
                    elif item.get('idShort') == 'InteractionMetadata':
                        for interaction in item.get('value', []):
                            if interaction.get('idShort') == 'properties':
                                for prop in interaction.get('value', []):
                                    prop_key = prop.get('idShort')
                                    prop_data = self._parse_property_definition(prop)
                                    if prop_data:
                                        properties[prop_key] = prop_data
        
        return endpoint_info, properties
    
    def _parse_property_definition(self, prop_elem: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parse a property definition from InterfaceMQTT"""
        prop_data = {'key': prop_elem.get('idShort')}
        
        for item in prop_elem.get('value', []):
            id_short = item.get('idShort')
            if id_short == 'output':
                # Schema file
                prop_data['schema_url'] = item.get('value', '')
            elif id_short == 'forms':
                # Extract href (MQTT topic suffix)
                for form_item in item.get('value', []):
                    if form_item.get('idShort') == 'href':
                        prop_data['topic_suffix'] = form_item.get('value', '')
        
        return prop_data if 'topic_suffix' in prop_data else None
    
    def _parse_interface_references(self, variables_sm: Dict[str, Any],
                                     interfaces_sm: Dict[str, Any],
                                     mqtt_properties: Dict[str, Dict]) -> Dict[str, Dict]:
        """
        Parse InterfaceReferences from Variables submodel.
        
        Returns dict mapping property paths to their MQTT topic and schema info:
        {
            "Variables/Weight.Value": {
                "topic": "NN/Nybrovej/InnoLab/Filling/DATA/Weight",
                "schema_url": "...",
                "value_type": "xs:double",
                "property_id_short": "Weight.Value"
            }
        }
        """
        refs = {}
        submodel_id_short = variables_sm.get('idShort')
        
        def process_element(elem, parent_path=""):
            """Recursively process elements looking for InterfaceReferences"""
            id_short = elem.get('idShort', '')
            model_type = elem.get('modelType', '')
            current_path = f"{parent_path}.{id_short}" if parent_path else id_short
            
            if model_type == 'Property':
                # This is a data property - check for sibling InterfaceReference
                return None
            
            elif model_type == 'SubmodelElementCollection':
                # Look for InterfaceReference in this collection
                has_interface_ref = False
                interface_ref_elem = None
                property_elems = []
                
                for child in elem.get('value', []):
                    if child.get('modelType') == 'ReferenceElement' and \
                       child.get('idShort') == 'InterfaceReference':
                        has_interface_ref = True
                        interface_ref_elem = child
                    elif child.get('modelType') == 'Property':
                        property_elems.append(child)
                
                if has_interface_ref and interface_ref_elem:
                    # Resolve the reference
                    ref_keys = interface_ref_elem.get('value', {}).get('keys', [])
                    mqtt_prop_key = self._resolve_reference_keys(ref_keys)
                    
                    if mqtt_prop_key and mqtt_prop_key in mqtt_properties:
                        mqtt_info = mqtt_properties[mqtt_prop_key]
                        
                        # Create entries for each Property in this collection
                        for prop_elem in property_elems:
                            prop_id = prop_elem.get('idShort')
                            prop_path = f"{current_path}.{prop_id}"
                            full_path = f"{submodel_id_short}/{prop_path}"
                            
                            refs[full_path] = {
                                'topic': mqtt_info.get('topic_suffix', ''),
                                'schema_url': mqtt_info.get('schema_url', ''),
                                'value_type': prop_elem.get('valueType', 'xs:string'),
                                'property_id_short': prop_path,
                                'mqtt_property_key': mqtt_prop_key
                            }
                            logger.debug(f"  Mapped {full_path} → {mqtt_info.get('topic_suffix')}")
                
                # Recurse into nested collections (not needed if InterfaceReference found)
                if not has_interface_ref:
                    for child in elem.get('value', []):
                        if child.get('modelType') in ['SubmodelElementCollection']:
                            process_element(child, current_path)
        
        # Process all elements in Variables submodel
        for elem in variables_sm.get('submodelElements', []):
            process_element(elem)
        
        return refs
    
    def _resolve_reference_keys(self, keys: List[Dict]) -> Optional[str]:
        """
        Resolve reference keys to extract the final property key.
        Keys structure: [..., {type: "SubmodelElementCollection", value: "properties"}, 
                        {type: "SubmodelElementCollection", value: "weight"}]
        """
        if not keys or len(keys) < 2:
            return None
        
        # The last key should be the property name
        return keys[-1].get('value')
    
    def _group_by_topic(self, interface_refs: Dict[str, Dict]) -> Dict[str, List[str]]:
        """
        Group property paths by their MQTT topic.
        
        Returns: {topic: [property_path1, property_path2, ...]}
        """
        groups = {}
        for prop_path, info in interface_refs.items():
            topic = info['topic']
            if topic not in groups:
                groups[topic] = []
            groups[topic].append(prop_path)
        
        return groups
    
    def _generate_consumers(self, topic_groups: Dict[str, List[str]], 
                           mqtt_endpoint: Dict[str, str]) -> List[Dict]:
        """Generate MQTT consumer configs - one per unique topic"""
        consumers = []
        
        base_topic = mqtt_endpoint.get('base_topic', '')
        
        for idx, topic_suffix in enumerate(sorted(topic_groups.keys())):
            full_topic = f"{base_topic}{topic_suffix}" if base_topic else topic_suffix
            
            # Generate consumer ID from topic
            consumer_id = f"mqtt_consumer_{idx + 1}"
            
            consumer = {
                "uniqueId": consumer_id,
                "serverUrl": self.mqtt_broker,
                "serverPort": self.mqtt_port,
                "topic": full_topic
            }
            consumers.append(consumer)
            logger.info(f"  Consumer {consumer_id}: {full_topic}")
        
        return consumers
    
    def _generate_transformers(self, interface_refs: Dict[str, Dict],
                               queries_dir: str) -> List[Dict]:
        """Generate JSONATA transformer configs with query files"""
        transformers = []
        
        for prop_path, info in interface_refs.items():
            # Create transformer ID
            transformer_id = prop_path.replace('/', '_').replace('.', '_').lower() + "_transformer"
            
            # Generate JSONATA query
            jsonata_query = self._create_jsonata_query(prop_path, info)
            
            # Write query file
            query_filename = f"{transformer_id}.jsonata"
            query_path = os.path.join(queries_dir, query_filename)
            with open(query_path, 'w') as f:
                f.write(jsonata_query)
            logger.debug(f"  Created {query_filename}: {jsonata_query}")
            
            transformer = {
                "uniqueId": transformer_id,
                "queryLanguage": "JSONATA",
                "queryPath": f"queries/{query_filename}",
                "inputType": "JsonString",
                "outputType": "JsonString"
            }
            transformers.append(transformer)
        
        return transformers
    
    def _create_jsonata_query(self, prop_path: str, info: Dict[str, Any]) -> str:
        """
        Create JSONATA query expression for extracting and converting data.
        
        Special handling for OccupationState:
        - State property: Derive from Occupation array length
        - Queue property: Convert Occupation array to string
        """
        value_type = info['value_type']
        schema_url = info.get('schema_url', '')
        
        # Special handling for OccupationState
        if 'OccupationState' in prop_path:
            if prop_path.endswith('.State'):
                # Derive "Available" or "Occupied" from Occupation array
                return '$count($.Occupation) > 0 ? "Occupied" : "Available"'
            elif prop_path.endswith('.Queue'):
                # Convert Occupation array to JSON string
                return '$string($.Occupation)'
        
        # Try to generate from schema
        if schema_url:
            try:
                jsonata = self._generate_from_schema(schema_url, value_type)
                if jsonata:
                    return jsonata
            except Exception as e:
                logger.warning(f"Failed to fetch schema {schema_url}: {e}")
        
        # Fallback to type-based conversion
        return self._jsonata_for_type(value_type)
    
    def _generate_from_schema(self, schema_url: str, value_type: str) -> Optional[str]:
        """Generate JSONATA by analyzing JSON schema"""
        response = requests.get(schema_url, timeout=5)
        if response.status_code != 200:
            return None
        
        schema = response.json()
        
        # Extract properties
        properties = {}
        required = []
        
        if 'allOf' in schema:
            for item in schema['allOf']:
                if 'properties' in item:
                    properties.update(item.get('properties', {}))
                if 'required' in item:
                    required.extend(item.get('required', []))
        else:
            properties = schema.get('properties', {})
            required = schema.get('required', [])
        
        # Find main data field (skip metadata like Timestamp, Uuid)
        data_field = None
        for field in required:
            if field not in ['Timestamp', 'Source', 'Uuid']:
                data_field = field
                break
        
        if not data_field and properties:
            for field in properties.keys():
                if field not in ['Timestamp', 'Source', 'Uuid']:
                    data_field = field
                    break
        
        if data_field:
            # Determine conversion based on value_type
            if value_type in ['xs:double', 'xs:float', 'xs:decimal', 'xs:integer', 'xs:int']:
                return f"$number($.{data_field})"
            elif value_type == 'xs:boolean':
                return f"$boolean($.{data_field})"
            else:
                return f"$string($.{data_field})"
        
        return None
    
    def _jsonata_for_type(self, value_type: str) -> str:
        """Generate JSONATA for type conversion"""
        type_map = {
            'xs:double': '$number($)',
            'xs:float': '$number($)',
            'xs:decimal': '$number($)',
            'xs:integer': '$number($)',
            'xs:int': '$number($)',
            'xs:boolean': '$boolean($)',
            'xs:string': '$string($)',
        }
        return type_map.get(value_type, '$string($)')
    
    def _generate_sinks(self, interface_refs: Dict[str, Dict],
                        variables_sm: Dict[str, Any],
                        basyx_url: str) -> List[Dict]:
        """Generate AAS server sink configs"""
        sinks = []
        
        # Get Variables submodel ID and encode it
        submodel_id = variables_sm.get('id', '')
        encoded_id = base64.b64encode(submodel_id.encode()).decode()
        
        for prop_path, info in interface_refs.items():
            # Extract property path (after "Variables/")
            if '/' in prop_path:
                _, id_short_path = prop_path.split('/', 1)
            else:
                id_short_path = info['property_id_short']
            
            sink = {
                "uniqueId": prop_path,
                "submodelEndpoint": f"{basyx_url}/submodels/{encoded_id}",
                "idShortPath": id_short_path,
                "api": "DotAasV3"
            }
            sinks.append(sink)
        
        return sinks
    
    def _generate_routes(self, topic_groups: Dict[str, List[str]],
                         interface_refs: Dict[str, Dict]) -> List[Dict]:
        """
        Generate route configs with multiple datasinks per topic.
        
        Key insight: One MQTT topic can update multiple AAS properties,
        so we create one route per topic with multiple transformers and datasinks.
        """
        routes = []
        
        for idx, (topic_suffix, prop_paths) in enumerate(sorted(topic_groups.items())):
            consumer_id = f"mqtt_consumer_{idx + 1}"
            
            # Build lists of transformers and datasinks for this route
            transformers = []
            datasinks = []
            datasink_mapping = {}
            
            for prop_path in prop_paths:
                transformer_id = prop_path.replace('/', '_').replace('.', '_').lower() + "_transformer"
                transformers.append(transformer_id)
                datasinks.append(prop_path)
                
                # Map this datasink to its transformer
                datasink_mapping[prop_path] = [transformer_id]
            
            route = {
                "datasource": consumer_id,
                "transformers": transformers,
                "datasinks": datasinks,
                "trigger": "event"
            }
            
            # Add datasinkMappingConfiguration if multiple sinks
            if len(datasinks) > 1:
                route["datasinkMappingConfiguration"] = datasink_mapping
            
            routes.append(route)
            logger.info(f"  Route {idx + 1}: {consumer_id} → {len(datasinks)} sink(s)")
        
        return routes
    
    def _write_json(self, filepath: str, data: Any):
        """Write JSON file with pretty formatting"""
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        logger.info(f"Wrote {filepath}")
