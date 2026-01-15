"""
MQTT Registration Interface

Listens for asset registration messages via MQTT and queues them for processing.
Handles concurrent registration requests and DataBridge restarts safely.
"""

import json
import logging
import queue
import threading
import time
from typing import Dict, Any, Optional
import paho.mqtt.client as mqtt

from .registry import BaSyxRegistrationService

logger = logging.getLogger(__name__)


class MQTTRegistrationService:
    """MQTT interface for asset registration with queueing"""
    
    def __init__(self, 
                 registration_service: BaSyxRegistrationService,
                 mqtt_broker: str = "192.168.0.104",
                 mqtt_port: int = 1883,
                 registration_topic: str = "NN/Nybrovej/InnoLab/Registration/Request",
                 response_topic: str = "NN/Nybrovej/InnoLab/Registration/Response",
                 client_id: str = "aas-registration-service"):
        """
        Initialize MQTT registration service
        
        Args:
            registration_service: BaSyxRegistrationService instance
            mqtt_broker: MQTT broker hostname/IP
            mqtt_port: MQTT broker port
            registration_topic: Topic to subscribe for registration requests
            response_topic: Topic to publish registration responses
            client_id: MQTT client ID
        """
        self.registration_service = registration_service
        self.mqtt_broker = mqtt_broker
        self.mqtt_port = mqtt_port
        self.registration_topic = registration_topic
        self.response_topic = response_topic
        self.client_id = client_id
        
        # Queue for registration requests
        self.registration_queue = queue.Queue()
        
        # Thread control
        self.running = False
        self.worker_thread = None
        self.mqtt_thread = None
        
        # MQTT client
        self.mqtt_client = None
        
        # Lock for DataBridge restart operations
        self.restart_lock = threading.Lock()
        
        # Statistics
        self.stats = {
            'received': 0,
            'processed': 0,
            'failed': 0,
            'queued': 0
        }
    
    def start(self):
        """Start MQTT listener and worker thread"""
        if self.running:
            logger.warning("MQTT registration service already running")
            return
        
        logger.info("Starting MQTT registration service...")
        self.running = True
        
        # Start worker thread for processing queue
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()
        
        # Start MQTT client
        self._start_mqtt_client()
        
        logger.info(f"MQTT registration service started on {self.mqtt_broker}:{self.mqtt_port}")
        logger.info(f"Listening on topic: {self.registration_topic}")
    
    def stop(self):
        """Stop MQTT listener and worker thread"""
        if not self.running:
            return
        
        logger.info("Stopping MQTT registration service...")
        self.running = False
        
        # Stop MQTT client
        if self.mqtt_client:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
        
        # Wait for worker to finish current task
        if self.worker_thread:
            self.worker_thread.join(timeout=30)
        
        logger.info("MQTT registration service stopped")
        logger.info(f"Final statistics: {self.stats}")
    
    def _start_mqtt_client(self):
        """Initialize and start MQTT client"""
        self.mqtt_client = mqtt.Client(client_id=self.client_id)
        
        # Set callbacks
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
    
    def _on_connect(self, client, userdata, flags, rc):
        """Callback when connected to MQTT broker"""
        if rc == 0:
            logger.info("Connected to MQTT broker successfully")
            # Subscribe to registration topic
            client.subscribe(self.registration_topic, qos=2)
            logger.info(f"Subscribed to topic: {self.registration_topic}")
        else:
            logger.error(f"Failed to connect to MQTT broker with code: {rc}")
    
    def _on_disconnect(self, client, userdata, rc):
        """Callback when disconnected from MQTT broker"""
        if rc != 0:
            logger.warning(f"Unexpected disconnect from MQTT broker: {rc}")
            # Paho MQTT loop_start() handles reconnection automatically
    
    def _on_message(self, client, userdata, msg):
        """Callback when message received"""
        try:
            self.stats['received'] += 1
            
            # Parse JSON payload
            payload = json.loads(msg.payload.decode('utf-8'))
            
            logger.info(f"Received registration request: {payload.get('assetId', 'unknown')}")
            
            # Validate message structure
            if not self._validate_registration_message(payload):
                logger.error(f"Invalid registration message format: {payload}")
                self._send_response(payload.get('requestId'), False, "Invalid message format")
                self.stats['failed'] += 1
                return
            
            # Add to queue
            self.registration_queue.put({
                'payload': payload,
                'timestamp': time.time()
            })
            
            self.stats['queued'] += 1
            queue_size = self.registration_queue.qsize()
            logger.info(f"Added to registration queue (queue size: {queue_size})")
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON message: {e}")
            self.stats['failed'] += 1
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            self.stats['failed'] += 1
    
    def _validate_registration_message(self, payload: Dict[str, Any]) -> bool:
        """Validate registration message structure"""
        if 'requestId' not in payload or 'aasData' not in payload:
            logger.error("Missing requestId or aasData")
            return False

        aas_data = payload['aasData']
        if not all(k in aas_data for k in ('assetAdministrationShells', 'submodels')):
            logger.error("Invalid aasData structure")
            return False
        
        # Auto-extract assetId if missing
        if not payload.get('assetId'):
            shells = aas_data.get('assetAdministrationShells', [])
            if shells:
                # Try idShort then id URL
                asset_id = shells[0].get('idShort', '').replace('AAS', '').replace('aas', '')
                if not asset_id:
                    asset_id = shells[0].get('id', '').split('/')[-1]
                
                payload['assetId'] = asset_id or 'unknown_asset'
                logger.info(f"Auto-extracted assetId: {payload['assetId']}")
        
        return True
    
    def _worker_loop(self):
        """Worker thread that processes registration queue"""
        logger.info("Registration worker thread started")
        
        while self.running:
            try:
                # Get next item from queue (timeout to allow checking self.running)
                try:
                    item = self.registration_queue.get(timeout=1.0)
                except queue.Empty:
                    continue
                
                payload = item['payload']
                request_id = payload.get('requestId')
                asset_id = payload.get('assetId')
                
                logger.info(f"Processing registration for asset: {asset_id}")
                
                # Acquire lock to ensure no concurrent DataBridge restarts
                with self.restart_lock:
                    success = self._process_registration(payload)
                
                if success:
                    logger.info(f"Successfully registered asset: {asset_id}")
                    self._send_response(request_id, True, f"Asset {asset_id} registered successfully")
                    self.stats['processed'] += 1
                else:
                    logger.error(f"Failed to register asset: {asset_id}")
                    self._send_response(request_id, False, f"Failed to register asset {asset_id}")
                    self.stats['failed'] += 1
                
                # Mark task as done
                self.registration_queue.task_done()
                
            except Exception as e:
                logger.error(f"Error in worker loop: {e}")
                self.stats['failed'] += 1
        
        logger.info("Registration worker thread stopped")
    
    def _process_registration(self, payload: Dict[str, Any]) -> bool:
        """
        Process a single registration request by delegating to the registration service.
        
        Args:
            payload: Registration message payload
        
        Returns:
            True if registration successful, False otherwise
        """
        try:
            asset_id = payload.get('assetId')
            aas_data = payload.get('aasData', {})
            
            # Extract shells, submodels, and concept descriptions
            shells = aas_data.get('assetAdministrationShells', [])
            submodels = aas_data.get('submodels', [])
            concept_descriptions = aas_data.get('conceptDescriptions', [])
            
            logger.info(f"Registering asset {asset_id} with {len(shells)} shell(s), {len(submodels)} submodels")
            
            # Delegate to unified registration service
            return self.registration_service.register_from_json(
                submodels=submodels,
                shells=shells,
                concept_descriptions=concept_descriptions
            )
            
        except Exception as e:
            logger.error(f"Error processing registration: {e}", exc_info=True)
            return False
    
    def _send_response(self, request_id: str, success: bool, message: str):
        """
        Send registration response via MQTT
        
        Args:
            request_id: Request ID from original message
            success: Whether registration was successful
            message: Status message
        """
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
            
            logger.debug(f"Sent response for request {request_id}: {message}")
            
        except Exception as e:
            logger.error(f"Failed to send response: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get current statistics"""
        return {
            **self.stats,
            'queue_size': self.registration_queue.qsize(),
            'running': self.running
        }
