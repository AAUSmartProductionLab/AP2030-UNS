"""
MQTT Registration Listener for Unified Registration Service

Listens for asset registration messages via MQTT and processes YAML configurations.
Supports both full AAS JSON and lightweight YAML config transmission.
"""

import json
import logging
import queue
import threading
import time
from typing import Dict, Any, Optional
import paho.mqtt.client as mqtt
import yaml

from .unified_service import UnifiedRegistrationService

logger = logging.getLogger(__name__)


class MQTTConfigRegistrationService:
    """
    MQTT interface for config-based asset registration.

    Supports two message formats:
    1. YAML Config: Lightweight config data for on-device registration
    2. Full AAS JSON: Legacy format for backward compatibility
    """

    def __init__(self,
                 registration_service: UnifiedRegistrationService,
                 mqtt_broker: str = "192.168.0.104",
                 mqtt_port: int = 1883,
                 config_topic: str = "NN/Nybrovej/InnoLab/Registration/Config",
                 response_topic: str = "NN/Nybrovej/InnoLab/Registration/Response",
                 client_id: str = "unified-registration-service"):
        """
        Initialize MQTT registration listener.

        Args:
            registration_service: UnifiedRegistrationService instance
            mqtt_broker: MQTT broker hostname/IP
            mqtt_port: MQTT broker port
            config_topic: Topic for YAML config registration
            response_topic: Topic for registration responses
            client_id: MQTT client ID
        """
        self.registration_service = registration_service
        self.mqtt_broker = mqtt_broker
        self.mqtt_port = mqtt_port
        self.config_topic = config_topic
        self.response_topic = response_topic
        self.client_id = client_id

        # Queue for registration requests
        self.registration_queue = queue.Queue()

        # Thread control
        self.running = False
        self.worker_thread = None

        # MQTT client
        self.mqtt_client = None

        # Lock for service operations
        self.service_lock = threading.Lock()

        # Batch processing configuration
        # Wait this long after last message before restarting databridge
        self.batch_debounce_seconds = 2.0
        # Track when we need to restart databridge
        self._pending_databridge_restart = False
        self._last_registration_time = 0.0
        self._batch_processed_count = 0

        # Statistics
        self.stats = {
            'config_received': 0,
            'processed': 0,
            'failed': 0,
            'databridge_restarts': 0
        }

    def start(self):
        """Start MQTT listener and worker thread"""
        if self.running:
            logger.warning("MQTT registration service already running")
            return

        logger.info("Starting unified MQTT registration service...")
        self.running = True

        # Start worker thread
        self.worker_thread = threading.Thread(
            target=self._worker_loop, daemon=True)
        self.worker_thread.start()

        # Start MQTT client
        self._start_mqtt_client()

        logger.info(
            f"MQTT registration service started on {self.mqtt_broker}:{self.mqtt_port}")
        logger.info(f"Config topic: {self.config_topic}")

    def stop(self):
        """Stop MQTT listener and worker thread"""
        if not self.running:
            return

        logger.info("Stopping MQTT registration service...")
        self.running = False

        if self.mqtt_client:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()

        if self.worker_thread:
            self.worker_thread.join(timeout=30)

        logger.info("MQTT registration service stopped")
        logger.info(f"Final statistics: {self.stats}")

    def _start_mqtt_client(self):
        """Initialize and start MQTT client"""
        self.mqtt_client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=self.client_id
        )

        self.mqtt_client.on_connect = self._on_connect
        self.mqtt_client.on_message = self._on_message
        self.mqtt_client.on_disconnect = self._on_disconnect

        try:
            logger.info(
                f"Connecting to MQTT broker {self.mqtt_broker}:{self.mqtt_port}...")
            self.mqtt_client.connect(
                self.mqtt_broker, self.mqtt_port, keepalive=60)
            self.mqtt_client.loop_start()
        except Exception as e:
            logger.error(f"Failed to connect to MQTT broker: {e}")
            raise

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        """Callback when connected to MQTT broker"""
        if reason_code == 0:
            logger.info("Connected to MQTT broker")
            # Subscribe to config topic
            client.subscribe(self.config_topic, qos=2)
            logger.info(f"Subscribed to: {self.config_topic}")
        else:
            logger.error(f"Failed to connect: {reason_code}")

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        """Callback when disconnected"""
        if reason_code != 0:
            logger.warning(f"Unexpected disconnect: {reason_code}")

    def _on_message(self, client, userdata, msg):
        """Handle incoming MQTT messages"""
        try:
            topic = msg.topic
            payload_str = msg.payload.decode('utf-8')

            # Handle config registration messages
            if topic == self.config_topic:
                self.stats['config_received'] += 1
                self._handle_config_message(payload_str)
            else:
                logger.warning(f"Unknown topic: {topic}")

        except Exception as e:
            logger.error(f"Error processing message: {e}")
            self.stats['failed'] += 1

    def _handle_config_message(self, payload: str):
        """
        Handle YAML config registration message.

        Supports two formats:

        1. Raw YAML (from ESP32 devices):
           planarTableShuttle1AAS:
             idShort: ...
             ...

        2. JSON wrapper (from other clients):
           {
               "requestId": "unique-id",
               "assetId": "asset-identifier",
               "config": { ... yaml config as JSON ... }
           }

        Or YAML string in JSON wrapper:
           {
               "requestId": "unique-id",
               "assetId": "asset-identifier", 
               "configYaml": "planarTableShuttle1AAS:\n  idShort: ..."
           }
        """
        try:
            # First, try to parse as JSON (wrapper format)
            try:
                message = json.loads(payload)
                request_id = message.get('requestId', 'unknown')
                asset_id = message.get('assetId', 'unknown')

                # Get config data from JSON wrapper
                if 'config' in message:
                    config_data = message['config']
                elif 'configYaml' in message:
                    config_data = yaml.safe_load(message['configYaml'])
                else:
                    logger.error("No config or configYaml in JSON message")
                    self._send_response(request_id, False,
                                        "Missing config data")
                    return

            except json.JSONDecodeError:
                # Not JSON - try parsing as raw YAML (from ESP32 devices)
                logger.info("Parsing raw YAML config from device")
                config_data = yaml.safe_load(payload)

                # Extract asset ID from the YAML structure (first key is typically the AAS ID)
                if isinstance(config_data, dict) and len(config_data) > 0:
                    first_key = next(iter(config_data))
                    asset_id = config_data[first_key].get('idShort', first_key)
                    request_id = f"device-{asset_id}-{int(time.time())}"
                else:
                    logger.error(
                        "Invalid YAML structure - expected dict with asset definition")
                    return

            logger.info(f"Received config registration for: {asset_id}")

            # Add to queue
            self.registration_queue.put({
                'type': 'config',
                'request_id': request_id,
                'asset_id': asset_id,
                'config_data': config_data,
                'timestamp': time.time()
            })

        except yaml.YAMLError as e:
            logger.error(f"Invalid YAML in config message: {e}")
            self.stats['failed'] += 1
        except Exception as e:
            logger.error(f"Error processing config message: {e}")
            self.stats['failed'] += 1

    def _handle_legacy_message(self, payload: str):
        """
        Handle legacy AAS JSON registration message.

        Expected format:
        {
            "requestId": "unique-id",
            "assetId": "asset-identifier",
            "aasData": {
                "assetAdministrationShells": [...],
                "submodels": [...]
            }
        }
        """
        try:
            message = json.loads(payload)
            request_id = message.get('requestId', 'unknown')
            asset_id = message.get('assetId', 'unknown')
            aas_data = message.get('aasData', {})

            if not aas_data:
                logger.error("No aasData in legacy message")
                self._send_response(request_id, False, "Missing aasData")
                return

            logger.info(f"Received legacy registration for: {asset_id}")

            # Add to queue
            self.registration_queue.put({
                'type': 'legacy',
                'request_id': request_id,
                'asset_id': asset_id,
                'aas_data': aas_data,
                'timestamp': time.time()
            })

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in legacy message: {e}")
            self.stats['failed'] += 1

    def _worker_loop(self):
        """
        Worker thread that processes registration queue with batch optimization.

        Instead of restarting the databridge after every registration, this worker:
        1. Processes all queued registrations without restarting databridge
        2. After the queue is empty and a debounce period passes, restarts databridge once

        This significantly improves performance when multiple assets register simultaneously.
        """
        logger.info("Registration worker started (batch mode enabled)")

        while self.running:
            try:
                # Get next item with timeout
                try:
                    item = self.registration_queue.get(timeout=0.5)
                except queue.Empty:
                    # Queue is empty - check if we need to restart databridge
                    self._check_pending_databridge_restart()
                    continue

                request_id = item.get('request_id')
                asset_id = item.get('asset_id')
                msg_type = item.get('type')

                logger.info(
                    f"Processing {msg_type} registration for: {asset_id} "
                    f"(queue size: {self.registration_queue.qsize()})")

                with self.service_lock:
                    if msg_type == 'config':
                        success = self._process_config_registration(item)
                    elif msg_type == 'legacy':
                        success = self._process_legacy_registration(item)
                    else:
                        success = False

                if success:
                    logger.info(f"Successfully registered: {asset_id}")
                    self._send_response(
                        request_id, True, f"Asset {asset_id} registered (databridge restart pending)")
                    self.stats['processed'] += 1
                    # Mark that we need to restart databridge and update timing
                    self._pending_databridge_restart = True
                    self._last_registration_time = time.time()
                    self._batch_processed_count += 1
                else:
                    logger.error(f"Failed to register: {asset_id}")
                    self._send_response(request_id, False,
                                        f"Registration failed for {asset_id}")
                    self.stats['failed'] += 1

                self.registration_queue.task_done()

            except Exception as e:
                logger.error(f"Worker error: {e}")
                self.stats['failed'] += 1

        # On shutdown, ensure final databridge restart if needed
        if self._pending_databridge_restart:
            self._do_databridge_restart()

        logger.info("Registration worker stopped")

    def _check_pending_databridge_restart(self):
        """
        Check if we should restart the databridge.

        Restart conditions:
        1. There are pending registrations that need databridge restart
        2. The queue is empty (all registrations processed)
        3. Enough time has passed since the last registration (debounce)
        """
        if not self._pending_databridge_restart:
            return

        # Check if queue is truly empty
        if not self.registration_queue.empty():
            return

        # Check debounce period
        time_since_last = time.time() - self._last_registration_time
        if time_since_last < self.batch_debounce_seconds:
            return

        # All conditions met - restart databridge
        self._do_databridge_restart()

    def _do_databridge_restart(self):
        """Perform the actual databridge restart and reset batch state."""
        try:
            batch_count = self._batch_processed_count
            logger.info(
                f"Restarting DataBridge after batch of {batch_count} registration(s)...")

            with self.service_lock:
                success = self.registration_service._restart_databridge()

            if success:
                logger.info(
                    f"✓ DataBridge restarted successfully for batch of {batch_count} asset(s)")
                self.stats['databridge_restarts'] += 1
            else:
                logger.error("DataBridge restart failed")

        except Exception as e:
            logger.error(f"Error restarting databridge: {e}")
        finally:
            # Reset batch state
            self._pending_databridge_restart = False
            self._batch_processed_count = 0

    def _process_config_registration(self, item: Dict[str, Any]) -> bool:
        """
        Process config-based registration without restarting services.

        The databridge restart is deferred until the batch is complete.
        """
        try:
            config_data = item.get('config_data')
            return self.registration_service.register_from_yaml_config(
                config_data=config_data,
                validate_aas=True,
                restart_services=False  # Defer restart until batch is complete
            )
        except Exception as e:
            logger.error(f"Config registration failed: {e}")
            return False

    def _process_legacy_registration(self, item: Dict[str, Any]) -> bool:
        """Process legacy AAS JSON registration"""
        try:
            aas_data = item.get('aas_data')
            # Use the direct registration method
            return self.registration_service._register_aas_with_basyx(aas_data)
        except Exception as e:
            logger.error(f"Legacy registration failed: {e}")
            return False

    def _send_response(self, request_id: str, success: bool, message: str):
        """Send registration response via MQTT"""
        try:
            response = {
                'requestId': request_id,
                'success': success,
                'message': message,
                'timestamp': time.time()
            }

            self.mqtt_client.publish(
                self.response_topic,
                json.dumps(response),
                qos=2,
                retain=False
            )

            logger.debug(f"Sent response for {request_id}: {message}")

        except Exception as e:
            logger.error(f"Failed to send response: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """Get current statistics including batch processing info"""
        return {
            **self.stats,
            'queue_size': self.registration_queue.qsize(),
            'running': self.running,
            'pending_databridge_restart': self._pending_databridge_restart,
            'batch_pending_count': self._batch_processed_count
        }
