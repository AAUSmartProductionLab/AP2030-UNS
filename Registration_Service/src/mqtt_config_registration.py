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
                 legacy_topic: str = "NN/Nybrovej/InnoLab/Registration/Request",
                 response_topic: str = "NN/Nybrovej/InnoLab/Registration/Response",
                 client_id: str = "unified-registration-service"):
        """
        Initialize MQTT registration listener.
        
        Args:
            registration_service: UnifiedRegistrationService instance
            mqtt_broker: MQTT broker hostname/IP
            mqtt_port: MQTT broker port
            config_topic: Topic for YAML config registration requests
            legacy_topic: Topic for legacy AAS JSON registration requests
            response_topic: Topic for registration responses
            client_id: MQTT client ID
        """
        self.registration_service = registration_service
        self.mqtt_broker = mqtt_broker
        self.mqtt_port = mqtt_port
        self.config_topic = config_topic
        self.legacy_topic = legacy_topic
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
        
        # Statistics
        self.stats = {
            'config_received': 0,
            'legacy_received': 0,
            'processed': 0,
            'failed': 0
        }
    
    def start(self):
        """Start MQTT listener and worker thread"""
        if self.running:
            logger.warning("MQTT registration service already running")
            return
        
        logger.info("Starting unified MQTT registration service...")
        self.running = True
        
        # Start worker thread
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()
        
        # Start MQTT client
        self._start_mqtt_client()
        
        logger.info(f"MQTT registration service started on {self.mqtt_broker}:{self.mqtt_port}")
        logger.info(f"Config topic: {self.config_topic}")
        logger.info(f"Legacy topic: {self.legacy_topic}")
    
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
            logger.info(f"Connecting to MQTT broker {self.mqtt_broker}:{self.mqtt_port}...")
            self.mqtt_client.connect(self.mqtt_broker, self.mqtt_port, keepalive=60)
            self.mqtt_client.loop_start()
        except Exception as e:
            logger.error(f"Failed to connect to MQTT broker: {e}")
            raise
    
    def _on_connect(self, client, userdata, flags, reason_code, properties):
        """Callback when connected to MQTT broker"""
        if reason_code == 0:
            logger.info("Connected to MQTT broker")
            # Subscribe to both topics
            client.subscribe(self.config_topic, qos=2)
            client.subscribe(self.legacy_topic, qos=2)
            logger.info(f"Subscribed to: {self.config_topic}, {self.legacy_topic}")
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
            
            # Determine message type based on topic
            if topic == self.config_topic:
                self.stats['config_received'] += 1
                self._handle_config_message(payload_str)
            elif topic == self.legacy_topic:
                self.stats['legacy_received'] += 1
                self._handle_legacy_message(payload_str)
            else:
                logger.warning(f"Unknown topic: {topic}")
                
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            self.stats['failed'] += 1
    
    def _handle_config_message(self, payload: str):
        """
        Handle YAML config registration message.
        
        Expected format:
        {
            "requestId": "unique-id",
            "assetId": "asset-identifier",
            "config": {
                "planarTableShuttle1AAS": {
                    "idShort": "...",
                    ...
                }
            }
        }
        
        Or YAML string:
        {
            "requestId": "unique-id",
            "assetId": "asset-identifier", 
            "configYaml": "planarTableShuttle1AAS:\n  idShort: ..."
        }
        """
        try:
            message = json.loads(payload)
            request_id = message.get('requestId', 'unknown')
            asset_id = message.get('assetId', 'unknown')
            
            # Get config data
            if 'config' in message:
                config_data = message['config']
            elif 'configYaml' in message:
                config_data = yaml.safe_load(message['configYaml'])
            else:
                logger.error("No config or configYaml in message")
                self._send_response(request_id, False, "Missing config data")
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
            
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in config message: {e}")
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
        """Worker thread that processes registration queue"""
        logger.info("Registration worker started")
        
        while self.running:
            try:
                # Get next item
                try:
                    item = self.registration_queue.get(timeout=1.0)
                except queue.Empty:
                    continue
                
                request_id = item.get('request_id')
                asset_id = item.get('asset_id')
                msg_type = item.get('type')
                
                logger.info(f"Processing {msg_type} registration for: {asset_id}")
                
                with self.service_lock:
                    if msg_type == 'config':
                        success = self._process_config_registration(item)
                    elif msg_type == 'legacy':
                        success = self._process_legacy_registration(item)
                    else:
                        success = False
                
                if success:
                    logger.info(f"Successfully registered: {asset_id}")
                    self._send_response(request_id, True, f"Asset {asset_id} registered")
                    self.stats['processed'] += 1
                else:
                    logger.error(f"Failed to register: {asset_id}")
                    self._send_response(request_id, False, f"Registration failed for {asset_id}")
                    self.stats['failed'] += 1
                
                self.registration_queue.task_done()
                
            except Exception as e:
                logger.error(f"Worker error: {e}")
                self.stats['failed'] += 1
        
        logger.info("Registration worker stopped")
    
    def _process_config_registration(self, item: Dict[str, Any]) -> bool:
        """Process config-based registration"""
        try:
            config_data = item.get('config_data')
            return self.registration_service.register_from_yaml_config(
                config_data=config_data,
                validate_aas=True
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
        """Get current statistics"""
        return {
            **self.stats,
            'queue_size': self.registration_queue.qsize(),
            'running': self.running
        }
