"""
Operation Delegation Flask API

This module provides the REST API for operation delegation, 
allowing BaSyx to invoke AAS Operations which are translated to MQTT commands.

The topic configuration is managed in-memory and can be updated dynamically
when new assets are registered.
"""

import os
import logging
import threading
from typing import Dict, Any, Optional

from flask import Flask, request, jsonify

from .mqtt_operation_bridge import MQTTOperationBridge

logger = logging.getLogger(__name__)

# Flask app for operation delegation
app = Flask(__name__)

# In-memory topic configuration (thread-safe access)
_topic_config: Dict[str, Any] = {}
_topic_config_lock = threading.Lock()

# Global MQTT bridge instance
_mqtt_bridge: Optional[MQTTOperationBridge] = None
_mqtt_bridge_lock = threading.Lock()


def get_topic_config() -> Dict[str, Any]:
    """Get the current topic configuration (thread-safe)."""
    with _topic_config_lock:
        return _topic_config.copy()


def update_topic_config(asset_id: str, config: Dict[str, Any]) -> None:
    """
    Update topic configuration for an asset (thread-safe).
    
    Args:
        asset_id: The asset identifier
        config: The configuration dict with base_topic, submodel_id, skills
    """
    with _topic_config_lock:
        _topic_config[asset_id] = config
        logger.info(f"Updated topic config for {asset_id}: {len(config.get('skills', {}))} skills")


def set_full_topic_config(config: Dict[str, Any]) -> None:
    """
    Set the entire topic configuration (thread-safe).
    
    Args:
        config: The complete topic configuration
    """
    with _topic_config_lock:
        _topic_config.clear()
        _topic_config.update(config)
        logger.info(f"Set full topic config with {len(config)} assets")


def get_mqtt_bridge(broker_host: str = None, broker_port: int = None) -> MQTTOperationBridge:
    """Get or create the global MQTT bridge instance"""
    global _mqtt_bridge
    with _mqtt_bridge_lock:
        if _mqtt_bridge is None:
            _mqtt_bridge = MQTTOperationBridge(
                broker_host=broker_host or os.environ.get("MQTT_BROKER", "localhost"),
                broker_port=broker_port or int(os.environ.get("MQTT_PORT", "1883")),
                timeout_seconds=float(os.environ.get("OPERATION_TIMEOUT", "30")),
                aas_server_url=os.environ.get("AAS_SERVER_URL")
            )
        # Try to connect if not connected
        if not _mqtt_bridge._connected.is_set():
            try:
                _mqtt_bridge.connect()
            except Exception as e:
                logger.warning(f"MQTT not connected yet: {e}")
        return _mqtt_bridge


def init_mqtt_bridge(broker_host: str, broker_port: int) -> None:
    """Initialize the MQTT bridge with specific broker settings."""
    global _mqtt_bridge
    with _mqtt_bridge_lock:
        if _mqtt_bridge is not None:
            # Disconnect existing bridge
            try:
                _mqtt_bridge.disconnect()
            except:
                pass
        _mqtt_bridge = MQTTOperationBridge(
            broker_host=broker_host,
            broker_port=broker_port,
            timeout_seconds=float(os.environ.get("OPERATION_TIMEOUT", "30")),
            aas_server_url=os.environ.get("AAS_SERVER_URL")
        )
        logger.info(f"Initialized MQTT bridge for {broker_host}:{broker_port}")


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
    topic_count = len(get_topic_config())
    return jsonify({
        "status": "healthy",
        "mqtt_connected": mqtt_connected,
        "registered_assets": topic_count
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
    from the in-memory configuration.

    Operation type is determined from config:
    - oneWay: true - Fire-and-forget, no response expected
    - synchronous: false - Asynchronous operation, update StateMachine property
    - Default (neither set): Synchronous operation, wait for single response

    Body: Array of OperationVariable objects
    """
    try:
        # Load topic mapping from in-memory config
        topic_config = get_topic_config()

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
        
        # Extract configuration from skill config
        array_mappings = skill_config.get('array_mappings')  # Will be None if not specified
        schema_url = skill_config.get('input_schema')  # The MQTT input schema URL
        output_schema_url = skill_config.get('output_schema')  # The MQTT output schema URL

        # Check if this is a one-way (fire-and-forget) operation
        # One-way operations explicitly have no response_topic in the config
        # If skill_config is empty (asset not registered), assume synchronous operation
        is_one_way = skill_config and 'response_topic' not in skill_config
        
        if is_one_way:
            # Fire-and-forget: publish and return immediately
            bridge = get_mqtt_bridge()
            bridge.invoke_one_way(command_topic, input_variables, array_mappings, schema_url)
            logger.info(f"One-way operation sent to {command_topic}")
            return jsonify([]), 200

        # Check if this is an async operation from config
        # Default to synchronous (synchronous=true means is_async=false)
        is_async = skill_config.get('synchronous', True) == False

        # Build state property path for async operations
        state_property_path: Optional[str] = None
        if is_async:
            # Get submodel_id from asset config, or derive from convention
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
            array_mappings=array_mappings,
            schema_url=schema_url,
            output_schema_url=output_schema_url
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


def start_delegation_api(host: str = "0.0.0.0", port: int = 8087):
    """
    Start the operation delegation Flask API in the current thread.
    
    Args:
        host: Host to bind to
        port: Port to listen on
    """
    # Start background thread to establish MQTT connection
    mqtt_thread = threading.Thread(
        target=try_connect_mqtt_background, daemon=True)
    mqtt_thread.start()

    logger.info(f"Starting Operation Delegation API on {host}:{port}")
    app.run(host=host, port=port, debug=False, threaded=True)


def start_delegation_api_background(
    host: str = "0.0.0.0", 
    port: int = 8087,
    mqtt_broker: str = None,
    mqtt_port: int = None
) -> threading.Thread:
    """
    Start the operation delegation Flask API in a background thread.
    
    Args:
        host: Host to bind to
        port: Port to listen on
        mqtt_broker: MQTT broker hostname
        mqtt_port: MQTT broker port
        
    Returns:
        The thread running the Flask app
    """
    # Initialize MQTT bridge with provided settings
    if mqtt_broker and mqtt_port:
        init_mqtt_bridge(mqtt_broker, mqtt_port)
    
    # Start background thread to establish MQTT connection
    mqtt_thread = threading.Thread(
        target=try_connect_mqtt_background, daemon=True)
    mqtt_thread.start()

    def run_app():
        logger.info(f"Starting Operation Delegation API on {host}:{port}")
        # Use werkzeug's threaded server in production-like mode
        from werkzeug.serving import make_server
        server = make_server(host, port, app, threaded=True)
        server.serve_forever()

    api_thread = threading.Thread(target=run_app, daemon=True)
    api_thread.start()
    
    logger.info(f"Operation Delegation API started on {host}:{port}")
    return api_thread
