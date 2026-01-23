"""
MQTT Operation Bridge for AAS Operations

This module provides the bridge between BaSyx AAS Operations and MQTT-controlled assets.
When an AAS Operation is invoked, BaSyx forwards the request to this service,
which translates it into MQTT messages and waits for the response.

Based on the BaSyx Operation Delegation pattern:
https://wiki.basyx.org/en/latest/content/concepts/use_cases/aas_operations.html
"""

import json
import uuid
import logging
import threading
import base64
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import requests
import paho.mqtt.client as mqtt

from .schema_parser import SchemaParser, determine_field_mappings

logger = logging.getLogger(__name__)


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

    # Terminal states that indicate operation completion
    TERMINAL_STATES = {"SUCCESS", "FAILURE", "ERROR", "COMPLETED", "ABORTED", "CANCELLED"}

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
        
        # Schema parser for automatic structure determination
        self.schema_parser = SchemaParser()

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
        array_mappings: Dict[str, List[Dict[str, str]]] = None,
        schema_url: Optional[str] = None,
        output_schema_url: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Invoke an operation by publishing an MQTT command and waiting for response.

        Args:
            command_topic: The MQTT topic to publish the command to
            response_topic: The MQTT topic to listen for the response
            input_variables: List of AAS OperationVariable objects
            is_async: Whether this is an asynchronous operation (updates AAS state property)
            state_property_path: For async ops, the path to update state: "submodel_id|skill_name"
            array_mappings: Optional dict for packing/unpacking arrays
            schema_url: Optional URL to MQTT input schema for auto-determining structure
            output_schema_url: Optional URL to MQTT output schema for response type conversion

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
            # Build MQTT command message from input variables
            command_message = self._build_command_message(
                correlation_id, input_variables, array_mappings, schema_url)

            # Log the generated message with schema compliance info
            if schema_url:
                logger.info(f"Generated MQTT message for topic {command_topic} (schema: {schema_url}):")
                logger.info(f"  Message: {json.dumps(command_message, indent=2)}")
            else:
                logger.warning(f"No schema available for {command_topic} - message may not be schema-compliant!")
                logger.info(f"  Unvalidated message: {json.dumps(command_message, indent=2)}")

            # Compute simple_mappings from output schema for response type conversion
            output_simple_mappings = {}
            if output_schema_url:
                try:
                    output_structure = self.schema_parser.extract_message_structure(output_schema_url)
                    # For output, we just need the field types for response conversion
                    # Build mappings from output schema field types
                    for field_name, field_info in output_structure.get("field_types", {}).items():
                        output_simple_mappings[field_name] = {
                            "aas_field": field_name,
                            "type": field_info.get("type"),
                            "format": field_info.get("format")
                        }
                    logger.info(f"Output schema simple mappings: {output_simple_mappings}")
                except Exception as e:
                    logger.warning(f"Failed to parse output schema {output_schema_url}: {e}")

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
                return self._build_response_variables(pending_op.response_data, array_mappings, output_simple_mappings)
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
        self,
        command_topic: str,
        input_variables: List[Dict[str, Any]],
        array_mappings: Dict[str, List[Dict[str, str]]] = None,
        schema_url: Optional[str] = None
    ) -> None:
        """
        Invoke a one-way (fire-and-forget) operation.

        Publishes the command and returns immediately without waiting for a response.
        Used for operations like halt, stop, reset that don't expect responses.

        Args:
            command_topic: The MQTT topic to publish the command to
            input_variables: List of AAS OperationVariable objects
            array_mappings: Optional dict for packing arrays
            schema_url: Optional URL to MQTT schema for auto-determining structure
        """
        # Generate correlation ID (still useful for logging/tracking)
        correlation_id = str(uuid.uuid4())

        # Build MQTT command message from input variables
        command_message = self._build_command_message(
            correlation_id, input_variables, array_mappings, schema_url)

        # Publish command (fire-and-forget)
        logger.info(
            f"Publishing one-way command to {command_topic}: {command_message}")
        result = self.client.publish(
            command_topic, json.dumps(command_message), qos=1)
        result.wait_for_publish()
        logger.info(
            f"One-way operation {correlation_id} published successfully")

    def _coerce_string_to_type(
        self,
        value: str,
        expected_type: str,
        field_name: str
    ) -> Any:
        """
        Coerce a string value to the expected type (array or object).
        
        BaSyx UI may send arrays/objects as JSON strings, or single values
        that need to be wrapped in an array.
        
        Args:
            value: The string value from AAS input
            expected_type: The expected type from schema ('array' or 'object')
            field_name: Field name for logging purposes
            
        Returns:
            The coerced value (list, dict, or original string on failure)
        """
        stripped = value.strip()
        
        if expected_type == "array":
            # Try to parse as JSON array first
            if stripped.startswith('['):
                try:
                    parsed = json.loads(stripped)
                    if isinstance(parsed, list):
                        logger.debug(f"Parsed JSON array string for '{field_name}': {parsed}")
                        return parsed
                except json.JSONDecodeError:
                    pass
            
            # If not parseable as array, wrap single value in array
            # (e.g., "https://example.com" -> ["https://example.com"])
            logger.debug(f"Wrapping single string value in array for '{field_name}'")
            return [value]
            
        elif expected_type == "object":
            # Try to parse as JSON object
            if stripped.startswith('{'):
                try:
                    parsed = json.loads(stripped)
                    if isinstance(parsed, dict):
                        logger.debug(f"Parsed JSON object string for '{field_name}': {parsed}")
                        return parsed
                except json.JSONDecodeError:
                    logger.warning(
                        f"Field '{field_name}' looks like JSON object but failed to parse: {stripped[:100]}"
                    )
            else:
                logger.warning(
                    f"Field '{field_name}' expected object type but received non-JSON string"
                )
        
        # Return original value if coercion fails
        return value

    def _build_command_message(
        self,
        correlation_id: str,
        input_variables: List[Dict[str, Any]],
        array_mappings: Dict[str, List[Dict[str, str]]] = None,
        schema_url: Optional[str] = None
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
        
        If schema_url is provided and array_mappings is not, the schema will be parsed
        to automatically determine the message structure. Only fields defined in the
        schema will be included in the MQTT message - AAS fields not in the schema
        will be dropped with a warning to ensure strict schema compliance.
        
        If array_mappings is provided, it will pack flattened fields back into arrays.
        For example: X, Y, Theta -> Position: [X, Y, Theta]
        
        Args:
            correlation_id: Unique ID for the command
            input_variables: AAS operation input variables
            array_mappings: Optional dict of parent_field -> [{aas_field, json_field, index, optional, default}]
            schema_url: Optional URL to MQTT schema for auto-determining structure
        """
        command = {
            "Uuid": correlation_id
        }

        # Extract values from OperationVariables
        field_values = {}
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

                field_values[id_short] = value
        
        # Auto-determine array mappings from schema if not provided
        simple_mappings = {}
        if schema_url and not array_mappings:
            try:
                logger.info(f"Parsing schema to determine message structure: {schema_url}")
                schema_structure = self.schema_parser.extract_message_structure(schema_url)
                
                # Determine mappings based on available AAS fields
                aas_fields = list(field_values.keys())
                array_mappings, simple_mappings, unmapped = determine_field_mappings(aas_fields, schema_structure)
                
                if array_mappings:
                    logger.info(f"Auto-determined array mappings: {array_mappings}")
                if simple_mappings:
                    logger.info(f"Auto-determined simple mappings: {simple_mappings}")
                if unmapped:
                    logger.warning(
                        f"AAS fields not in MQTT schema (will be dropped): {unmapped}. "
                        f"Schema: {schema_url}"
                    )
                    
            except Exception as e:
                logger.warning(f"Failed to parse schema {schema_url}: {e}. Continuing without schema-based mappings.")
                array_mappings = None
                simple_mappings = {}

        # Add simple mapped fields to command
        for schema_field, mapping_info in simple_mappings.items():
            aas_field = mapping_info["aas_field"]
            if aas_field in field_values:
                value = field_values[aas_field]
                expected_type = mapping_info.get("type")
                
                # Handle type coercion when schema expects array/object but input is string
                if isinstance(value, str) and expected_type in ("array", "object"):
                    value = self._coerce_string_to_type(value, expected_type, schema_field)
                
                command[schema_field] = value

        # Pack arrays if array_mappings is provided
        packed_fields = set(m["aas_field"] for m in simple_mappings.values())  # Track fields already used
        if array_mappings:
            
            for parent_field, mappings in array_mappings.items():
                # Sort by index to ensure correct order
                sorted_mappings = sorted(mappings, key=lambda m: m.get('index', 0))
                array_values = []
                all_required_present = True
                
                for mapping in sorted_mappings:
                    aas_field = mapping['aas_field']
                    is_optional = mapping.get('optional', False)
                    default_value = mapping.get('default')
                    
                    if aas_field in field_values:
                        array_values.append(field_values[aas_field])
                        packed_fields.add(aas_field)
                    elif is_optional:
                        # Use default for optional fields
                        if default_value is not None:
                            array_values.append(default_value)
                        # If no default and optional, stop here (truncate array)
                        else:
                            break
                    else:
                        # Required field missing
                        all_required_present = False
                        logger.warning(f"Required field '{aas_field}' missing for array '{parent_field}'")
                        break
                
                # Pack array if all required fields present
                if all_required_present and array_values:
                    command[parent_field] = array_values
            
            # Check for unmapped fields (not in schema) - log warning but DON'T include
            unmapped = set(field_values.keys()) - packed_fields
            if unmapped:
                logger.warning(
                    f"AAS fields not in MQTT schema (will be dropped): {sorted(unmapped)}. "
                    f"These fields are defined in the AAS but not in the MQTT schema '{schema_url}'."
                )
        else:
            # No array packing - when no schema is parsed, pass through all fields
            # This maintains backward compatibility for operations without schemas
            command.update(field_values)

        return command

    def _build_response_variables(
        self,
        response_data: Dict[str, Any],
        array_mappings: Dict[str, List[Dict[str, str]]] = None,
        simple_mappings: Dict[str, Dict[str, Any]] = None
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
        
        If array_mappings is provided, it will unpack arrays into flattened fields.
        For example: Position: [{X, Y, Theta}] -> Position_X, Position_Y, Position_Theta
        
        Args:
            response_data: MQTT response data
            array_mappings: Optional dict of parent_field -> [{aas_field, json_field}]
            simple_mappings: Optional dict with format info for type conversion
        """
        # Unpack arrays if array_mappings is provided
        flattened_data = {}
        
        if array_mappings:
            unpacked_fields = set()  # Track which fields have been unpacked
            
            for parent_field, mappings in array_mappings.items():
                if parent_field in response_data:
                    value = response_data[parent_field]
                    
                    # Unpack positional array [x, y, theta] -> X, Y, Theta
                    if isinstance(value, list) and len(value) > 0:
                        for mapping in mappings:
                            aas_field = mapping['aas_field']
                            index = mapping['index']
                            
                            if index < len(value):
                                flattened_data[aas_field] = value[index]
                        
                        unpacked_fields.add(parent_field)
            
            # Add remaining fields that weren't unpacked
            for field_name, field_value in response_data.items():
                if field_name not in unpacked_fields:
                    flattened_data[field_name] = field_value
        else:
            # No array unpacking, just pass through
            flattened_data = response_data
        
        # Build output variables from flattened data
        output_variables = []
        
        # Build reverse lookup: aas_field -> format info
        format_lookup = {}
        if simple_mappings:
            for schema_field, mapping_info in simple_mappings.items():
                aas_field = mapping_info["aas_field"]
                format_lookup[aas_field] = {
                    "type": mapping_info.get("type"),
                    "format": mapping_info.get("format")
                }
        
        for key, value in flattened_data.items():
            # Determine value type from schema format or infer from Python type
            format_info = format_lookup.get(key, {})
            json_format = format_info.get("format")
            json_type = format_info.get("type")
            
            # Map JSON Schema format to AAS valueType
            if json_format == "date-time":
                value_type = "xs:dateTime"
                str_value = str(value)
            elif json_format == "date":
                value_type = "xs:date"
                str_value = str(value)
            elif json_format == "time":
                value_type = "xs:time"
                str_value = str(value)
            elif json_format == "uri":
                value_type = "xs:anyURI"
                str_value = str(value)
            elif json_type == "integer":
                value_type = "xs:int"
                str_value = str(value)
            elif json_type == "number":
                value_type = "xs:double"
                str_value = str(value)
            elif json_type == "boolean":
                value_type = "xs:boolean"
                str_value = str(value).lower()
            elif isinstance(value, bool):
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
