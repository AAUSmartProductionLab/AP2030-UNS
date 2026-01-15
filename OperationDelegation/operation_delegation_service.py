"""
MQTT Operation Delegation Service for BaSyx AAS Operations

This service acts as a bridge between BaSyx AAS Operations and MQTT-controlled assets.
When an AAS Operation is invoked, BaSyx forwards the request to this service,
which translates it into MQTT messages and waits for the response.

Based on the BaSyx Operation Delegation pattern:
https://wiki.basyx.org/en/latest/content/concepts/use_cases/aas_operations.html
"""

import os
import json
import uuid
import logging
import threading
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from flask import Flask, request, jsonify
import paho.mqtt.client as mqtt

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)


@dataclass
class PendingOperation:
    """Tracks a pending operation waiting for MQTT response"""
    correlation_id: str
    created_at: datetime
    response_topic: str
    response_received: threading.Event = field(default_factory=threading.Event)
    response_data: Optional[Dict] = None
    response_state: str = "PENDING"


class MQTTOperationBridge:
    """
    Bridge between HTTP Operation invocations and MQTT messaging.
    
    Handles:
    1. Receiving AAS Operation invocations via HTTP
    2. Translating operation inputs to MQTT command messages
    3. Publishing commands to the appropriate MQTT topics
    4. Waiting for and correlating MQTT responses
    5. Returning responses as AAS OperationVariable format
    """
    
    def __init__(
        self,
        broker_host: str = "localhost",
        broker_port: int = 1883,
        client_id: str = "aas-operation-bridge",
        timeout_seconds: float = 30.0
    ):
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.client_id = client_id
        self.timeout_seconds = timeout_seconds
        
        # Thread-safe dictionary of pending operations
        self._pending_operations: Dict[str, PendingOperation] = {}
        self._lock = threading.Lock()
        
        # Topic to pending operation mapping (for response correlation)
        self._response_subscriptions: Dict[str, str] = {}
        
        # MQTT Client setup
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"{client_id}-{uuid.uuid4().hex[:8]}"
        )
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect
        
        self._connected = threading.Event()
        
    def connect(self):
        """Connect to MQTT broker"""
        logger.info(f"Connecting to MQTT broker at {self.broker_host}:{self.broker_port}")
        try:
            self.client.connect(self.broker_host, self.broker_port, 60)
            self.client.loop_start()
            # Wait for connection
            if not self._connected.wait(timeout=10):
                raise ConnectionError("Failed to connect to MQTT broker within timeout")
            logger.info("Successfully connected to MQTT broker")
        except Exception as e:
            logger.error(f"Failed to connect to MQTT broker: {e}")
            raise
            
    def disconnect(self):
        """Disconnect from MQTT broker"""
        self.client.loop_stop()
        self.client.disconnect()
        logger.info("Disconnected from MQTT broker")
        
    def _on_connect(self, client, userdata, flags, reason_code, properties):
        """Handle MQTT connection"""
        if reason_code == 0:
            logger.info("Connected to MQTT broker")
            self._connected.set()
        else:
            logger.error(f"Failed to connect to MQTT broker: {reason_code}")
            
    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        """Handle MQTT disconnection"""
        logger.warning(f"Disconnected from MQTT broker: {reason_code}")
        self._connected.clear()
        
    def _on_message(self, client, userdata, message):
        """Handle incoming MQTT messages (responses)"""
        topic = message.topic
        try:
            payload = json.loads(message.payload.decode('utf-8'))
            logger.info(f"Received message on {topic}: {payload}")
            
            # Find the pending operation for this response
            with self._lock:
                correlation_id = self._response_subscriptions.get(topic)
                if correlation_id and correlation_id in self._pending_operations:
                    operation = self._pending_operations[correlation_id]
                    operation.response_data = payload
                    operation.response_state = payload.get("State", "SUCCESS")
                    operation.response_received.set()
                    logger.info(f"Matched response to operation {correlation_id}")
                else:
                    logger.warning(f"No pending operation found for topic {topic}")
                    
        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode MQTT message: {e}")
        except Exception as e:
            logger.error(f"Error processing MQTT message: {e}")
            
    def invoke_operation(
        self,
        command_topic: str,
        response_topic: str,
        input_variables: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Invoke an operation by publishing an MQTT command and waiting for response.
        
        Args:
            command_topic: The MQTT topic to publish the command to
            response_topic: The MQTT topic to listen for the response
            input_variables: List of AAS OperationVariable objects
            
        Returns:
            List of AAS OperationVariable objects as response
        """
        # Generate correlation ID (Uuid in our command schema)
        correlation_id = str(uuid.uuid4())
        
        # Create pending operation
        pending_op = PendingOperation(
            correlation_id=correlation_id,
            created_at=datetime.now(),
            response_topic=response_topic
        )
        
        # Register for response
        with self._lock:
            self._pending_operations[correlation_id] = pending_op
            self._response_subscriptions[response_topic] = correlation_id
            
        # Subscribe to response topic
        self.client.subscribe(response_topic, qos=2)
        logger.info(f"Subscribed to response topic: {response_topic}")
        
        try:
            # Build MQTT command message from input variables
            command_message = self._build_command_message(correlation_id, input_variables)
            
            # Publish command
            logger.info(f"Publishing command to {command_topic}: {command_message}")
            result = self.client.publish(command_topic, json.dumps(command_message), qos=2)
            result.wait_for_publish()
            
            # Wait for response
            if pending_op.response_received.wait(timeout=self.timeout_seconds):
                logger.info(f"Received response for operation {correlation_id}")
                return self._build_response_variables(pending_op.response_data)
            else:
                logger.warning(f"Operation {correlation_id} timed out")
                raise TimeoutError(f"Operation timed out after {self.timeout_seconds} seconds")
                
        finally:
            # Cleanup
            with self._lock:
                self._pending_operations.pop(correlation_id, None)
                self._response_subscriptions.pop(response_topic, None)
            self.client.unsubscribe(response_topic)
            
    def _build_command_message(
        self,
        correlation_id: str,
        input_variables: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Build an MQTT command message from AAS OperationVariables.
        
        The input_variables follow the AAS OperationVariable format:
        [
            {
                "value": {
                    "modelType": "Property",
                    "idShort": "ParameterName",
                    "valueType": "xs:string",
                    "value": "actual_value"
                }
            },
            ...
        ]
        """
        command = {
            "Uuid": correlation_id
        }
        
        # Extract values from OperationVariables
        for var in input_variables:
            if "value" in var:
                value_obj = var["value"]
                id_short = value_obj.get("idShort", "")
                value = value_obj.get("value")
                value_type = value_obj.get("valueType", "xs:string")
                
                # Convert value based on type
                if value_type in ["xs:int", "xs:integer"]:
                    value = int(value) if value else 0
                elif value_type in ["xs:double", "xs:float", "xs:decimal"]:
                    value = float(value) if value else 0.0
                elif value_type == "xs:boolean":
                    value = str(value).lower() == "true"
                    
                command[id_short] = value
                
        return command
        
    def _build_response_variables(
        self,
        response_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Build AAS OperationVariable response from MQTT response data.
        
        Returns the response in the format BaSyx expects:
        [
            {
                "value": {
                    "modelType": "Property",
                    "idShort": "ResponseField",
                    "valueType": "xs:string",
                    "value": "response_value"
                }
            },
            ...
        ]
        """
        output_variables = []
        
        for key, value in response_data.items():
            # Determine value type
            if isinstance(value, bool):
                value_type = "xs:boolean"
                str_value = str(value).lower()
            elif isinstance(value, int):
                value_type = "xs:int"
                str_value = str(value)
            elif isinstance(value, float):
                value_type = "xs:double"
                str_value = str(value)
            else:
                value_type = "xs:string"
                str_value = str(value)
                
            output_variables.append({
                "value": {
                    "modelType": "Property",
                    "idShort": key,
                    "valueType": value_type,
                    "value": str_value
                }
            })
            
        return output_variables


# Global bridge instance
mqtt_bridge: Optional[MQTTOperationBridge] = None
mqtt_bridge_lock = threading.Lock()


def get_mqtt_bridge() -> MQTTOperationBridge:
    """Get or create the global MQTT bridge instance"""
    global mqtt_bridge
    with mqtt_bridge_lock:
        if mqtt_bridge is None:
            mqtt_bridge = MQTTOperationBridge(
                broker_host=os.environ.get("MQTT_BROKER", "localhost"),
                broker_port=int(os.environ.get("MQTT_PORT", "1883")),
                timeout_seconds=float(os.environ.get("OPERATION_TIMEOUT", "30"))
            )
        # Try to connect if not connected
        if not mqtt_bridge._connected.is_set():
            try:
                mqtt_bridge.connect()
            except Exception as e:
                logger.warning(f"MQTT not connected yet: {e}")
        return mqtt_bridge


def try_connect_mqtt_background():
    """Try to connect to MQTT in background with retries"""
    max_retries = 30
    retry_delay = 5
    
    for attempt in range(max_retries):
        try:
            bridge = get_mqtt_bridge()
            if bridge._connected.is_set():
                logger.info("MQTT connection established in background")
                return
        except Exception as e:
            logger.warning(f"MQTT connection attempt {attempt + 1}/{max_retries} failed: {e}")
        
        import time
        time.sleep(retry_delay)
    
    logger.error("Failed to establish MQTT connection after all retries")


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    bridge = get_mqtt_bridge()
    mqtt_connected = bridge._connected.is_set() if bridge else False
    return jsonify({
        "status": "healthy",
        "mqtt_connected": mqtt_connected
    }), 200


@app.route('/invoke/<path:skill_path>', methods=['POST'])
def invoke_operation(skill_path: str):
    """
    Generic operation invocation endpoint.
    
    The skill_path is used to derive the MQTT topics:
    - Command topic: Derived from the path or provided in headers
    - Response topic: Derived from command topic + /Response
    
    Expected headers:
    - X-Command-Topic: MQTT topic to send command to
    - X-Response-Topic: MQTT topic to listen for response (optional)
    
    Body: Array of OperationVariable objects
    """
    try:
        # Get MQTT topics from headers or derive from path
        command_topic = request.headers.get('X-Command-Topic')
        response_topic = request.headers.get('X-Response-Topic')
        
        if not command_topic:
            # Derive from skill path
            # skill_path format: <asset>/<skill_name>
            # e.g., planarShuttle1/MoveToPosition
            command_topic = f"NN/Nybrovej/InnoLab/{skill_path.replace('/', '/CMD/')}"
            
        if not response_topic:
            # Derive response topic from command topic
            response_topic = command_topic.replace('/CMD/', '/DATA/')
            
        logger.info(f"Invoking operation - Command: {command_topic}, Response: {response_topic}")
        
        # Parse input variables
        input_variables = request.get_json() or []
        
        # Invoke via MQTT bridge
        bridge = get_mqtt_bridge()
        result = bridge.invoke_operation(command_topic, response_topic, input_variables)
        
        return jsonify(result), 200
        
    except TimeoutError as e:
        logger.error(f"Operation timeout: {e}")
        return jsonify({
            "error": "Operation timed out",
            "message": str(e)
        }), 504
    except Exception as e:
        logger.error(f"Operation invocation failed: {e}")
        return jsonify({
            "error": "Operation failed",
            "message": str(e)
        }), 500


@app.route('/operations/<asset_id>/<skill_name>', methods=['POST'])
def invoke_asset_skill(asset_id: str, skill_name: str):
    """
    Invoke a specific skill on an asset.
    
    URL format: /operations/<asset_id>/<skill_name>
    Example: /operations/planarShuttle1/MoveToPosition
    
    The asset_id and skill_name are used to look up the MQTT topic mapping
    from a configuration or derive it from conventions.
    
    Body: Array of OperationVariable objects
    """
    try:
        # Load topic mapping from config or environment
        topic_config = load_topic_config()
        
        # Look up or derive topics
        if asset_id in topic_config:
            asset_config = topic_config[asset_id]
            if skill_name in asset_config.get("skills", {}):
                skill_config = asset_config["skills"][skill_name]
                command_topic = skill_config.get("command_topic")
                response_topic = skill_config.get("response_topic")
            else:
                # Derive from base topic
                base_topic = asset_config.get("base_topic", f"NN/Nybrovej/InnoLab/{asset_id}")
                command_topic = f"{base_topic}/CMD/{skill_name}"
                response_topic = f"{base_topic}/DATA/{skill_name}"
        else:
            # Use default convention
            command_topic = f"NN/Nybrovej/InnoLab/{asset_id}/CMD/{skill_name}"
            response_topic = f"NN/Nybrovej/InnoLab/{asset_id}/DATA/{skill_name}"
            
        logger.info(f"Invoking {skill_name} on {asset_id} - Command: {command_topic}, Response: {response_topic}")
        
        # Parse input variables
        input_variables = request.get_json() or []
        
        # Invoke via MQTT bridge
        bridge = get_mqtt_bridge()
        result = bridge.invoke_operation(command_topic, response_topic, input_variables)
        
        return jsonify(result), 200
        
    except TimeoutError as e:
        logger.error(f"Operation timeout: {e}")
        return jsonify({
            "error": "Operation timed out",
            "message": str(e)
        }), 504
    except Exception as e:
        logger.error(f"Operation invocation failed: {e}")
        return jsonify({
            "error": "Operation failed",
            "message": str(e)
        }), 500


def load_topic_config() -> Dict[str, Any]:
    """
    Load MQTT topic configuration from file or environment.
    
    The configuration maps asset IDs and skills to MQTT topics.
    """
    config_path = os.environ.get("TOPIC_CONFIG_PATH", "/app/config/topics.json")
    
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            return json.load(f)
    else:
        # Return empty config, topics will be derived from conventions
        return {}


def main():
    """Main entry point"""
    # Start background thread to establish MQTT connection
    mqtt_thread = threading.Thread(target=try_connect_mqtt_background, daemon=True)
    mqtt_thread.start()
    
    # Run Flask app (starts immediately, even if MQTT not connected yet)
    port = int(os.environ.get("PORT", "8087"))
    host = os.environ.get("HOST", "0.0.0.0")
    
    logger.info(f"Starting Operation Delegation Service on {host}:{port}")
    app.run(host=host, port=port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
