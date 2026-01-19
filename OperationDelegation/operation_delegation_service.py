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
import base64
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import requests
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
    # For async operations: path to update state property in AAS
    state_property_path: Optional[str] = None
    is_async: bool = False


class AASStateUpdater:
    """
    Updates AAS SubmodelElement properties via HTTP PATCH.

    Used to update the StateMachine property for asynchronous operations.
    """

    def __init__(self, aas_server_url: str):
        """
        Initialize the AAS state updater.

        Args:
            aas_server_url: Base URL of the AAS server (e.g., "http://aas-server:8081")
        """
        self.aas_server_url = aas_server_url.rstrip('/')

    def update_state_machine(self, submodel_id: str, skill_name: str, state: str) -> bool:
        """
        Update the StateMachine property for an async operation.

        Args:
            submodel_id: The ID of the Skills submodel
            skill_name: Name of the skill (SubmodelElementCollection)
            state: The new state value (IDLE, RUNNING, SUCCESS, FAILURE)

        Returns:
            True if update was successful, False otherwise
        """
        try:
            # Encode submodel ID for URL
            encoded_submodel_id = base64.urlsafe_b64encode(
                submodel_id.encode()
            ).decode().rstrip('=')

            # Build the path to the StateMachine property
            # Path: /submodels/{submodelId}/submodel-elements/{skillName}.StateMachine
            id_short_path = f"{skill_name}.StateMachine"

            url = (
                f"{self.aas_server_url}/submodels/{encoded_submodel_id}"
                f"/submodel-elements/{id_short_path}/$value"
            )

            # PATCH the value
            response = requests.patch(
                url,
                json=state,
                headers={"Content-Type": "application/json"},
                timeout=5
            )

            if response.status_code in [200, 204]:
                logger.info(
                    f"Updated StateMachine to '{state}' for {skill_name}")
                return True
            else:
                logger.warning(
                    f"Failed to update StateMachine: {response.status_code} - {response.text}"
                )
                return False

        except requests.RequestException as e:
            logger.error(f"Error updating AAS state: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error updating AAS state: {e}")
            return False


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
        timeout_seconds: float = 30.0,
        aas_server_url: Optional[str] = None
    ):
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.client_id = client_id
        self.timeout_seconds = timeout_seconds

        # AAS state updater for async operations
        self.aas_state_updater: Optional[AASStateUpdater] = None
        if aas_server_url:
            self.aas_state_updater = AASStateUpdater(aas_server_url)

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
        logger.info(
            f"Connecting to MQTT broker at {self.broker_host}:{self.broker_port}")
        try:
            self.client.connect(self.broker_host, self.broker_port, 60)
            self.client.loop_start()
            # Wait for connection
            if not self._connected.wait(timeout=10):
                raise ConnectionError(
                    "Failed to connect to MQTT broker within timeout")
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

    # Terminal states that indicate operation completion
    TERMINAL_STATES = {"SUCCESS", "FAILURE",
                       "ERROR", "COMPLETED", "ABORTED", "CANCELLED"}

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
                    state = payload.get("State", "SUCCESS").upper()

                    # Always update the response data with the latest
                    operation.response_data = payload
                    operation.response_state = state

                    # For async operations, update the AAS StateMachine property
                    if operation.is_async and operation.state_property_path:
                        self._update_aas_state_async(
                            operation.state_property_path, state)

                    # Only signal completion for terminal states
                    if state in self.TERMINAL_STATES:
                        operation.response_received.set()
                        logger.info(
                            f"Operation {correlation_id} completed with state: {state}")
                    else:
                        logger.info(
                            f"Operation {correlation_id} intermediate state: {state} - waiting for terminal state")
                else:
                    logger.warning(
                        f"No pending operation found for topic {topic}")

        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode MQTT message: {e}")
        except Exception as e:
            logger.error(f"Error processing MQTT message: {e}")

    def _update_aas_state_async(self, state_property_path: str, state: str):
        """
        Update AAS StateMachine property in a separate thread to avoid blocking.

        Args:
            state_property_path: Tuple of (submodel_id, skill_name) or formatted path
            state: The new state value
        """
        if not self.aas_state_updater:
            logger.warning(
                "AAS state updater not configured, skipping state update")
            return

        # Capture the updater reference for the closure
        aas_updater = self.aas_state_updater

        def update():
            try:
                # state_property_path format: "submodel_id|skill_name"
                parts = state_property_path.split("|")
                if len(parts) == 2:
                    submodel_id, skill_name = parts
                    logger.info(
                        f"Updating AAS state: submodel={submodel_id}, skill={skill_name}, state={state}")
                    aas_updater.update_state_machine(
                        submodel_id, skill_name, state)
                else:
                    logger.error(
                        f"Invalid state_property_path format: {state_property_path}")
            except Exception as e:
                logger.error(f"Failed to update AAS state: {e}")

        # Run in background to avoid blocking MQTT message handling
        threading.Thread(target=update, daemon=True).start()

    def invoke_operation(
        self,
        command_topic: str,
        response_topic: str,
        input_variables: List[Dict[str, Any]],
        is_async: bool = False,
        state_property_path: Optional[str] = None,
        array_mappings: Optional[Dict[str, List[str]]] = None
    ) -> List[Dict[str, Any]]:
        """
        Invoke an operation by publishing an MQTT command and waiting for response.

        Args:
            command_topic: The MQTT topic to publish the command to
            response_topic: The MQTT topic to listen for the response
            input_variables: List of AAS OperationVariable objects
            is_async: Whether this is an asynchronous operation (updates AAS state property)
            array_mappings: Optional dict mapping array names to field names for transformation
            state_property_path: For async ops, the path to update state: "submodel_id|skill_name"

        Returns:
            List of AAS OperationVariable objects as response
        """
        # Generate correlation ID (Uuid in our command schema)
        correlation_id = str(uuid.uuid4())

        # Create pending operation
        pending_op = PendingOperation(
            correlation_id=correlation_id,
            created_at=datetime.now(),
            response_topic=response_topic,
            is_async=is_async,
            state_property_path=state_property_path
        )

        # For async operations, set initial state to RUNNING
        if is_async and state_property_path:
            self._update_aas_state_async(state_property_path, "RUNNING")

        # Register for response
        with self._lock:
            self._pending_operations[correlation_id] = pending_op
            self._response_subscriptions[response_topic] = correlation_id

        # Subscribe to response topic
        self.client.subscribe(response_topic, qos=2)
        logger.info(f"Subscribed to response topic: {response_topic}")

        try:
            # Build MQTT command message from i, array_mappings)

            # Publish command
            logger.info(
                f"Publishing command to {command_topic}: {command_message}")
            result = self.client.publish(
                command_topic, json.dumps(command_message), qos=2)
            result.wait_for_publish()

            # Wait for response
            if pending_op.response_received.wait(timeout=self.timeout_seconds):
                logger.info(
                    f"Received response for operation {correlation_id}")
                # For async operations, reset state to IDLE after completion
                if is_async and state_property_path:
                    # State was already updated by _on_message, now set to IDLE
                    self._update_aas_state_async(state_property_path, "IDLE")
                return self._build_response_variables(pending_op.response_data, array_mappingsE
                    self._update_aas_state_async(state_property_path, "IDLE")
                return self._build_response_variables(pending_op.response_data)
            else:
                logger.warning(f"Operation {correlation_id} timed out")
                # Update state to indicate timeout/failure
                if is_async and state_property_path:
                    self._update_aas_state_async(
                        state_property_path, "TIMEOUT")
                raise TimeoutError(
                    f"Operation timed out after {self.timeout_seconds} seconds")

        finally:
            # Cleanup
            with self._lock:
                self._pending_operations.pop(correlation_id, None)
                self._response_subscriptions.pop(response_topic, None)
            self.client.unsubscribe(response_topic)

    def invoke_one_way(
        self,,
        array_mappings: Optional[Dict[str, List[str]]] = None
    ) -> None:
        """
        Invoke a one-way (fire-and-forget) operation.

        Publishes the command and returns immediately without waiting for a response.
        Used for operations like halt, stop, reset that don't expect responses.

        Args:
            command_topic: The MQTT topic to publish the command to
            input_variables: List of AAS OperationVariable objects
            array_mappings: Optional dict mapping array names to field names for transformation
        """
        # Generate correlation ID (still useful for logging/tracking)
        correlation_id = str(uuid.uuid4())

        # Build MQTT command message from input variables
        command_message = self._build_command_message(
            correlation_id, input_variables, array_mappinginput variables
        command_message = self._build_command_message(
            correlation_id, input_variables)

        # Publish command (fire-and-forget)
        logger.info(
            f"Publishing one-way command to {command_topic}: {command_message}")
        result = self.client.publish(
            command_topic, json.dumps(command_message), qos=1)
        result.wait_for_publish()
        logger.info(
            f"One-way operation {correlation_id} published successfully")

    def _build_command_message(
        self,
        correlation_id: str,
        input_variables: List[Dict[str, Any]],
        array_mappings: Optional[Dict[str, List[str]]] = None
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
        
        Args:
            correlation_id: UUID for the command
            input_variables: AAS OperationVariables
            array_mappings: Optional dict mapping array names to their component fields.
                           Example: {"Position": ["X", "Y", "Theta"]}
                           Fields are combined in the order specified.
        """
        command = {
            "Uuid": correlation_id
        }

        # Default array mappings if not provided
        if array_mappings is None:
            array_mappings = {
                "Position": ["X", "Y", "Theta"]
            }

        # Collect all values first
        values = {}
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

                values[id_short] = value

        # Apply array mappings: combine individual fields into arrays
        for array_name, field_names in array_mappings.items():
            array_values = []
            for field_name in field_names:
                if field_name in values:
                    array_values.append(values.pop(field_name))
            
            # Only add the array if at least one component was present
            if array_values:
                command[array_name] = array_values

        # Add remaining values to command
        command.update(values)

        return command

    def _build_response_variables(
        self,
        response_data: Dict[str, Any],
        array_mappings: Optional[Dict[str, List[str]]] = None
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
        
        Args:
            response_data: MQTT response data
            array_mappings: Optional dict mapping array names to their component fields.
                           Example: {"Position": ["X", "Y", "Theta"]}
                           Arrays are unpacked into individual fields in the order specified.
        """
        # Default array mappings if not provided
        if array_mappings is None:
            array_mappings = {
                "Position": ["X", "Y", "Theta"]
            }
        
        # Make a copy to avoid modifying the original
        data = dict(response_data)

        # Unpack arrays into individual fields based on mappings
        for array_name, field_names in array_mappings.items():
            if array_name in data and isinstance(data[array_name], list):
                array_values = data.pop(array_name)
                for i, field_name in enumerate(field_names):
                    if i < len(array_values):
                        data[field_name] = array_values[i]

        output_variables = []
        for key, value in data.items():
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
                timeout_seconds=float(
                    os.environ.get("OPERATION_TIMEOUT", "30")),
                aas_server_url=os.environ.get("AAS_SERVER_URL")
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
            logger.warning(
                f"MQTT connection attempt {attempt + 1}/{max_retries} failed: {e}")

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

        logger.info(
            f"Invoking operation - Command: {command_topic}, Response: {response_topic}")

        # Parse input variables
        input_variables = request.get_json() or []

        # Invoke via MQTT bridge
        bridge = get_mqtt_bridge()
        result = bridge.invoke_operation(
            command_topic, response_topic, input_variables)

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

    Operation type is determined from topics.json config:
    - oneWay: true - Fire-and-forget, no response expected
    - synchronous: false - Asynchronous operation, update StateMachine property
    - Default (neither set): Synchronous operation, wait for single response

    Headers (for additional context):
    - X-Skills-Submodel-Id: Submodel ID for async state updates (optional)

    Body: Array of OperationVariable objects
    """
    try:
        # Load topic mapping from config or environment
        topic_config = load_topic_config()

        # Default skill config values
        skill_config: Dict[str, Any] = {}
        command_topic: str
        response_topic: str

        # Look up or derive topics
        if asset_id in topic_config:
            asset_config = topic_config[asset_id]
            if skill_name in asset_config.get("skills", {}):
                skill_config = asset_config["skills"][skill_name]
                command_topic = skill_config.get(
                    "command_topic", f"NN/Nybrovej/InnoLab/{asset_id}/CMD/{skill_name}")
                response_topic = skill_config.get(
                    "response_topic", f"NN/Nybrovej/InnoLab/{asset_id}/DATA/{skill_name}")
            else:
                # Derive from base topic
                base_topic = asset_config.get(
                    "base_topic", f"NN/Nybrovej/InnoLab/{asset_id}")
                command_topic = f"{base_topic}/CMD/{skill_name}"
                response_topic = f"{base_topic}/DATA/{skill_name}"
        else:
            # Use default convention
            command_topic = f"NN/Nybrovej/InnoLab/{asset_id}/CMD/{skill_name}"
            response_topic = f"NN/Nybrovej/InnoLab/{asset_id}/DATA/{skill_name}"

        logger.info(
            f"Invoking {skill_name} on {asset_id} - Command: {command_topic}, Response: {response_topic}")
        logger.debug(f"Skill config: {skill_config}")

        # Parse input variables
        input_variables = request.get_json() or []

        # Check if this is a one-way (fire-and-forget) operation
        # One-way operations have no response_topic in the config
        is_one_way = 'response_topic' not in skill_config
        # Get array mappings from skill config
        array_mappings = skill_config.get('array_mappings')
        
        if is_one_way:
            # Fire-and-forget: publish and return immediately
            bridge = get_mqtt_bridge()
            bridge.invoke_one_way(command_topic, input_variables, array_mappings)
            logger.info(f"One-way operation sent to {command_topic}")
            return jsonify([]), 200

        # Check if this is an async operation from config
        # Default to synchronous (synchronous=true means is_async=false)
        is_async = skill_config.get('synchronous', True) == False

        # Build state property path for async operations
        state_property_path: Optional[str] = None
        if is_async:
            # Get submodel_id from asset config in topics.json, or derive from convention
            asset_config = topic_config.get(asset_id, {})
            submodel_id = asset_config.get('submodel_id')
            if not submodel_id:
                # Derive from base URL convention
                base_url = os.environ.get(
                    "AAS_BASE_URL", "https://smartproductionlab.aau.dk")
                submodel_id = f"{base_url}/submodels/instances/{asset_id}/Skills"
            state_property_path = f"{submodel_id}|{skill_name}"
            logger.info(
                f"Async operation - will update state at: {state_property_path}")

        # Invoke via MQTT bridge
        bridge = get_mqtt_bridge()
        result = bridge.invoke_operation(
            command_topic,
            response_topic,
            input_variables,
            is_async=is_async,
            state_property_path=state_property_path,
            array_mappings=array_mappings
            input_variables,
            is_async=is_async,
            state_property_path=state_property_path
        )

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
    config_path = os.environ.get(
        "TOPIC_CONFIG_PATH", "/app/config/topics.json")

    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            config = json.load(f)
            logger.debug(f"Loaded topic config with {len(config)} assets")
            return config
    else:
        # Return empty config, topics will be derived from conventions
        logger.warning(
            f"Topic config file not found at {config_path}, using defaults")
        return {}


def main():
    """Main entry point"""
    # Start background thread to establish MQTT connection
    mqtt_thread = threading.Thread(
        target=try_connect_mqtt_background, daemon=True)
    mqtt_thread.start()

    # Run Flask app (starts immediately, even if MQTT not connected yet)
    port = int(os.environ.get("PORT", "8087"))
    host = os.environ.get("HOST", "0.0.0.0")

    logger.info(f"Starting Operation Delegation Service on {host}:{port}")
    app.run(host=host, port=port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
