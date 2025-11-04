"""
BaSyx DataBridge Configuration Generator

Generates MQTT consumer, AAS server, JSONATA transformer, and route configurations
for the Eclipse BaSyx DataBridge with automatic type conversion based on AAS schemas.
"""

import base64
import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


class DataBridgeConfigGenerator:
    """Generates BaSyx Databridge configurations"""

    def __init__(self, mqtt_broker: str = "hivemq-broker", mqtt_port: int = 1883):
        self.mqtt_broker = mqtt_broker
        self.mqtt_port = mqtt_port

    def generate_mqtt_consumer_config(self, submodels: List[Dict[str, Any]], topic_mappings: Optional[Dict[str, str]] = None, interface_info: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Generate MQTT consumer configuration with optional custom topic mappings and interface info.
        
        If interface_info contains actions from InterfaceMQTT, generates consumers for those topics.
        Otherwise, falls back to property-based topic generation.
        """
        consumers = []

        # If interface_info has actions, generate consumers based on InterfaceMQTT
        if interface_info and interface_info.get('actions'):
            logger.info("Generating MQTT consumers from InterfaceMQTT actions")
            
            for action_name, action_data in interface_info['actions'].items():
                # Create consumer for request topic (subscribe to commands)
                if action_data.get('request_topic'):
                    consumer = {
                        "uniqueId": f"action_{action_name}_request",
                        "serverUrl": self.mqtt_broker,
                        "serverPort": self.mqtt_port,
                        "topic": action_data['request_topic']
                    }
                    consumers.append(consumer)
                    logger.debug(f"  Added consumer for action '{action_name}' request: {action_data['request_topic']}")
                
                # Create consumers for additional topics (e.g., data publications)
                for idx, add_topic in enumerate(action_data.get('additional_topics', [])):
                    consumer = {
                        "uniqueId": f"action_{action_name}_additional_{idx}",
                        "serverUrl": self.mqtt_broker,
                        "serverPort": self.mqtt_port,
                        "topic": add_topic
                    }
                    consumers.append(consumer)
                    logger.debug(f"  Added consumer for action '{action_name}' additional topic: {add_topic}")
            
            # Add consumers for properties if available
            for prop_name, prop_data in interface_info.get('properties', {}).items():
                if prop_data.get('topic') and prop_data.get('direction') == 'subscribe':
                    consumer = {
                        "uniqueId": f"property_{prop_name}",
                        "serverUrl": self.mqtt_broker,
                        "serverPort": self.mqtt_port,
                        "topic": prop_data['topic']
                    }
                    consumers.append(consumer)
                    logger.debug(f"  Added consumer for property '{prop_name}': {prop_data['topic']}")
        
        else:
            # Fallback: Generate consumers based on submodel properties
            logger.info("Generating MQTT consumers from submodel properties (no InterfaceMQTT found)")
            
            # Create reverse mapping from property path to topic
            reverse_mappings = {}
            if topic_mappings:
                for topic, prop_path in topic_mappings.items():
                    reverse_mappings[prop_path] = topic

            for submodel in submodels:
                submodel_short = submodel.get('idShort', 'unknown')
                
                # Skip InterfaceMQTT submodels themselves
                if 'Interface' in submodel_short:
                    continue

                for element in submodel.get('submodelElements', []):
                    prop_short = element.get('idShort', '')
                    prop_path = f"{submodel_short}/{prop_short}"

                    # Use custom topic mapping if provided, otherwise generate default
                    if prop_path in reverse_mappings:
                        topic = reverse_mappings[prop_path]
                    else:
                        # Generate default MQTT topic based on submodel and property
                        topic = f"sensors/{submodel_short.lower()}/{prop_short.lower()}"

                    consumer = {
                        "uniqueId": f"{submodel_short}_{prop_short}_sensor",
                        "serverUrl": self.mqtt_broker,
                        "serverPort": self.mqtt_port,
                        "topic": topic
                    }
                    consumers.append(consumer)

        return consumers

    def generate_aas_server_config(self, submodels: List[Dict[str, Any]], basyx_config) -> List[Dict[str, Any]]:
        """Generate AAS server configuration for databridge"""
        server_configs = []

        for submodel in submodels:
            submodel_id = submodel.get('id', '')
            submodel_short = submodel.get('idShort', 'unknown')

            # Encode submodel ID to base64 for URL
            encoded_id = base64.b64encode(submodel_id.encode()).decode()

            for element in submodel.get('submodelElements', []):
                prop_short = element.get('idShort', '')

                config = {
                    "uniqueId": f"{submodel_short}/{prop_short}",
                    "submodelEndpoint": f"http://aas-env:8081/submodels/{encoded_id}",
                    "idShortPath": prop_short,
                    "api": "DotAasV3"
                }
                server_configs.append(config)

        return server_configs

    def generate_jsonata_transformers(self, submodels: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Generate JSONATA transformers based on AAS property value types"""
        transformers = []

        for submodel in submodels:
            submodel_short = submodel.get('idShort', 'unknown')

            for element in submodel.get('submodelElements', []):
                prop_short = element.get('idShort', '')
                value_type = element.get('valueType', 'xs:string')
                
                # Generate JSONATA expression based on valueType
                jsonata_expression = self._get_jsonata_for_type(value_type)
                
                transformer = {
                    "uniqueId": f"{submodel_short}_{prop_short}_transformer",
                    "queryLanguage": "JSONATA",
                    "query": jsonata_expression
                }
                transformers.append(transformer)

        return transformers

    def _get_jsonata_for_type(self, value_type: str) -> str:
        """Generate JSONATA expression for type conversion based on AAS valueType"""
        # Map XSD types to JSONATA conversion expressions
        type_mapping = {
            # Numeric types
            'xs:double': '$number($)',
            'xs:float': '$number($)',
            'xs:decimal': '$number($)',
            'xs:integer': '$number($)',
            'xs:int': '$number($)',
            'xs:long': '$number($)',
            'xs:short': '$number($)',
            'xs:byte': '$number($)',
            'xs:unsignedLong': '$number($)',
            'xs:unsignedInt': '$number($)',
            'xs:unsignedShort': '$number($)',
            'xs:unsignedByte': '$number($)',
            'xs:positiveInteger': '$number($)',
            'xs:nonNegativeInteger': '$number($)',
            
            # Boolean type
            'xs:boolean': '$boolean($)',
            
            # String types
            'xs:string': '$string($)',
            'xs:normalizedString': '$string($)',
            'xs:token': '$string($)',
            
            # Date/Time types - keep as strings in ISO format
            'xs:dateTime': '$string($)',
            'xs:date': '$string($)',
            'xs:time': '$string($)',
            'xs:duration': '$string($)',
            
            # Other types
            'xs:anyURI': '$string($)',
            'xs:base64Binary': '$string($)',
            'xs:hexBinary': '$string($)',
        }
        
        # Return the appropriate conversion, default to string
        return type_mapping.get(value_type, '$string($)')

    def generate_routes_config(self, submodels: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Generate routes configuration with transformers"""
        routes = []

        for submodel in submodels:
            submodel_short = submodel.get('idShort', 'unknown')

            for element in submodel.get('submodelElements', []):
                prop_short = element.get('idShort', '')

                route = {
                    "datasource": f"{submodel_short}_{prop_short}_sensor",
                    "transformers": [f"{submodel_short}_{prop_short}_transformer"],
                    "datasinks": [f"{submodel_short}/{prop_short}"],
                    "trigger": "event"
                }
                routes.append(route)

        return routes
