import enum
import datetime
import threading # Add this import
import inspect   # Add this import
from library.MQTT_classes import Proxy,Publisher, ResponseAsync, Topic


class PackMLState(enum.Enum):
    # Main states
    IDLE = "IDLE"
    STARTING = "STARTING"
    EXECUTE = "EXECUTE"
    COMPLETING = "COMPLETING"
    COMPLETE = "COMPLETE"
    RESETTING = "RESETTING"
    
    # Hold states
    HOLDING = "HOLDING"
    HELD = "HELD"
    UNHOLDING = "UNHOLDING"
    
    # Suspend states
    SUSPENDING = "SUSPENDING"
    SUSPENDED = "SUSPENDED"
    UNSUSPENDING = "UNSUSPENDING"
    
    # Stop and abort states
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    ABORTING = "ABORTING"
    ABORTED = "ABORTED"
    CLEARING = "CLEARING"


class PackMLStateMachine:
    def __init__(self,  base_topic, client:Proxy, properties):
        self.state = PackMLState.IDLE
        self.base_topic = base_topic
        self.running_execution = False # Keep if used elsewhere, otherwise consider removing
        # Mqtt stuff
        self.client = client
        self.properties = properties
        self.Uuid = None

        # ProcessQueue
        self.is_processing = False
        self.uuids = []  # Track all queued command UUIDs

        # UUID of the command currently in process_function
        self.current_processing_uuid = None
        self.processing_events = {}  # Stores threading.Event for interruptible processes
        # Tracks if complete was called for a UUID during its processing
        self.interruption_requested_for_uuid = {}

        # Stores original command UUID for pending registration confirmations
        # Key: UUID of the item in queue, Value: UUID of the original registration command
        self.pending_registrations = {}

        # Schemas assume . relative path from CWD. In container /app is CWD and schemas are in /app/schemas.
        # So ./MQTTSchema is correct if mapped correctly.
        self.register_topic = ResponseAsync(
            self.base_topic+"/DATA/Occupy",
            self.base_topic+"/CMD/Occupy",
            "./MQTTSchemacommandResponse.schema.json",
            "./MQTTSchemacommand.schema.json",
            2,
            self.register_callback
        )
        self.unregister_topic = ResponseAsync(
            self.base_topic+"/DATA/Release",
            self.base_topic+"/CMD/Release",
            "./MQTTSchemacommandResponse.schema.json",
            "./MQTTSchemacommand.schema.json",
            2,
            self.unregister_callback
        )

        # Add basic commands
        self.start_topic = ResponseAsync(
            self.base_topic+"/DATA/Start",
            self.base_topic+"/CMD/Start",
            "./MQTTSchemacommandResponse.schema.json",
            "./MQTTSchemacommand.schema.json",
            2,
            self.start_callback
        )

        self.stop_topic = ResponseAsync(
            self.base_topic+"/DATA/Stop",
            self.base_topic+"/CMD/Stop",
            "./MQTTSchemacommandResponse.schema.json",
            "./MQTTSchemacommand.schema.json",
            2,
            self.stop_callback
        )

        self.reset_topic = ResponseAsync(
            self.base_topic+"/DATA/Reset",
            self.base_topic+"/CMD/Reset",
            "./MQTTSchemacommandResponse.schema.json",
            "./MQTTSchemacommand.schema.json",
            2,
            self.reset_callback
        )

        self.hold_topic = ResponseAsync(
            self.base_topic+"/DATA/Hold",
            self.base_topic+"/CMD/Hold",
            "./MQTTSchemacommandResponse.schema.json",
            "./MQTTSchemacommand.schema.json",
            2,
            self.hold_callback
        )

        self.unhold_topic = ResponseAsync(
            self.base_topic+"/DATA/Unhold",
            self.base_topic+"/CMD/Unhold",
            "./MQTTSchemacommandResponse.schema.json",
            "./MQTTSchemacommand.schema.json",
            2,
            self.unhold_callback
        )

        self.state_topic = Publisher(
            self.base_topic+"/DATA/State",
            "./MQTTSchemastationState.schema.json",
            2
        )

        # Register basic PackML topics
        topics=[self.register_topic, self.unregister_topic, self.state_topic,
                self.start_topic, self.stop_topic, self.reset_topic, self.hold_topic, self.unhold_topic]
        for topic in topics:
            client.register_topic(topic)

        self.publish_state()

        # External handlers
        self.on_start = None
        self.on_stop = None
        self.on_reset = None
        self.on_hold = None
        self.on_unhold = None

    def _publish_command_status(self, status_topic_publisher, command_uuid, state_value):
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
        response = {
            "State": state_value,
            "TimeStamp": timestamp,
            "Uuid": command_uuid
        }
        status_topic_publisher.publish(response, self.client, False)

    def register_callback(self,topic, client, message, properties):
        print(f"PackML Register: {message}")

    def unregister_callback(self,topic, client, message, properties):
        print(f"PackML Unregister: {message}")

    def start_callback(self, topic, client, message, properties):
        print("Received Start command")
        if self.state == PackMLState.IDLE:
            self.set_state(PackMLState.STARTING)
            self._publish_command_status(topic, message.get("Uuid"), "SUCCESS")
            
            if self.on_start:
                try:
                    self.on_start()
                except Exception as e:
                    print(f"Error in on_start: {e}")
            
            self.set_state(PackMLState.EXECUTE)
        else:
             self._publish_command_status(topic, message.get("Uuid"), "FAILURE")

    def stop_callback(self, topic, client, message, properties):
        print("Received Stop command")
        # Stop is allowed from almost any state
        if self.state not in [PackMLState.STOPPED, PackMLState.STOPPING]:
            previous_state = self.state
            self.set_state(PackMLState.STOPPING)
            self._publish_command_status(topic, message.get("Uuid"), "SUCCESS")
            
            if self.on_stop:
                 try:
                    self.on_stop()
                 except Exception as e:
                    print(f"Error in on_stop: {e}")
            
            self.set_state(PackMLState.STOPPED)
        else:
             self._publish_command_status(topic, message.get("Uuid"), "SUCCESS") # Already stopped is success?

    def reset_callback(self, topic, client, message, properties):
        print("Received Reset command")
        if self.state in [PackMLState.STOPPED, PackMLState.COMPLETE, PackMLState.ABORTED]:
            self.set_state(PackMLState.RESETTING)
            self._publish_command_status(topic, message.get("Uuid"), "SUCCESS")
            
            if self.on_reset:
                 try:
                    self.on_reset()
                 except Exception as e:
                    print(f"Error in on_reset: {e}")
            
            self.set_state(PackMLState.IDLE)
        else:
             self._publish_command_status(topic, message.get("Uuid"), "FAILURE")

    def hold_callback(self, topic, client, message, properties):
        print("Received Hold command")
        if self.state == PackMLState.EXECUTE:
            self.set_state(PackMLState.HOLDING)
            self._publish_command_status(topic, message.get("Uuid"), "SUCCESS")
            
            if self.on_hold:
                 try:
                    self.on_hold()
                 except Exception as e:
                    print(f"Error in on_hold: {e}")
            
            self.set_state(PackMLState.HELD)
        else:
             self._publish_command_status(topic, message.get("Uuid"), "FAILURE")

    def unhold_callback(self, topic, client, message, properties):
        print("Received Unhold command")
        if self.state == PackMLState.HELD:
            self.set_state(PackMLState.UNHOLDING)
            self._publish_command_status(topic, message.get("Uuid"), "SUCCESS")
            
            if self.on_unhold:
                 try:
                    self.on_unhold()
                 except Exception as e:
                    print(f"Error in on_unhold: {e}")
            
            self.set_state(PackMLState.EXECUTE)
        else:
             self._publish_command_status(topic, message.get("Uuid"), "FAILURE")

    def set_state(self, state: PackMLState):
        self.state = state
        self.publish_state()

    def publish_state(self):
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
        message = {
            "State": self.state.value,
            "TimeStamp": timestamp
        }
        self.state_topic.publish(message, self.client)

    def get_state(self):
        return self.state
