import enum
import datetime
import threading # Add this import
import inspect   # Add this import
from MQTT_classes import Proxy,Publisher, ResponseAsync, Topic


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
        
        self.current_processing_uuid = None     # UUID of the command currently in process_function
        self.processing_events = {} # Stores threading.Event for interruptible processes
        self.interruption_requested_for_uuid = {} # Tracks if complete was called for a UUID during its processing

        # Stores original command UUID for pending registration confirmations
        # Key: UUID of the item in queue, Value: UUID of the original registration command
        self.pending_registrations = {}

        self.register_topic = ResponseAsync(
            self.base_topic+"/DATA/Register",
            self.base_topic+"/CMD/Register",
            "./schemas/commandResponse.schema.json", 
            "./schemas/command.schema.json", 
            2, 
            self.register_callback
        )
        self.unregister_topic = ResponseAsync(
            self.base_topic+"/DATA/Unregister",
            self.base_topic+"/CMD/Unregister",
            "./schemas/commandResponse.schema.json", 
            "./schemas/command.schema.json", 
            2, 
            self.unregister_callback
        )

        self.state_topic = Publisher(
            self.base_topic+"/DATA/State", 
            "./schemas/stationState.schema.json",
            2
        )
        topics=[self.register_topic, self.unregister_topic, self.state_topic]
        for topic in topics:
            client.register_topic(topic)

        self.publish_state()

    def _publish_command_status(self, status_topic_publisher, command_uuid, state_value):
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
        response = {
            "State": state_value,
            "TimeStamp": timestamp,
            "Uuid": command_uuid
        }
        status_topic_publisher.publish(response, self.client, False)

    def register_callback(self,topic, client, message, properties):
        """Callback handler for registering commands."""
        try:
            command_uuid = message.get("Uuid") # This is the UUID of the item to be queued
            if not command_uuid:
                print("Error in register_callback: Message missing Uuid.")
                # Optionally publish a generic error if possible, or log
                return
            
            # Publish RUNNING for the registration command itself
            self._publish_command_status(self.register_topic, command_uuid, "RUNNING")
            self.register_command(command_uuid) # Pass the UUID to be queued
            
        except Exception as e:
            print(f"Error in register_callback: {e}")
            # If command_uuid was parsed, publish FAILURE for it
            if 'command_uuid' in locals() and command_uuid:
                 self._publish_command_status(self.register_topic, command_uuid, "FAILURE")


    def unregister_callback(self,topic, client, message, properties):
        """Callback handler for unregistering commands."""
        try:  
            command_uuid = message.get("Uuid") # This is the UUID of the item to be unregistered
            if not command_uuid:
                print("Error in unregister_callback: Message missing Uuid.")
                return

            # Publish RUNNING for the unregistration command itself
            # Success/Failure will be published by unregister_command
            self._publish_command_status(self.unregister_topic, command_uuid, "RUNNING")
            self.unregister_command(command_uuid) # Pass the UUID to be unregistered
            
        except Exception as e:
            print(f"Error in unregister_callback: {e}")
            if 'command_uuid' in locals() and command_uuid:
                self._publish_command_status(self.unregister_topic, command_uuid, "FAILURE")


    def register_command(self, uuid_to_queue):
        """
        Registers a UUID. The registration command itself is considered RUNNING
        until the item reaches the head of the queue (SUCCESS) or is removed/fails (FAILURE).
        """
        if uuid_to_queue in self.uuids or uuid_to_queue == self.current_processing_uuid:
            self._publish_command_status(self.register_topic, uuid_to_queue, "FAILURE") # Reason: Duplicate/Already active
            print(f"Registration failed for {uuid_to_queue}: Already registered or active.")
            return

        self.uuids.append(uuid_to_queue)
        self.pending_registrations[uuid_to_queue] = uuid_to_queue # Map item UUID to its own command UUID for status
        
        self.publish_state() # Update observers about the new queue state

        if self.state == PackMLState.IDLE: # If IDLE, and this is the first item
            self.transition_to(PackMLState.STARTING)
        # If not IDLE, or if other items were already queued, the RUNNING status persists.
        # starting_state will handle publishing SUCCESS when this uuid_to_queue reaches the front.

    def unregister_command(self, uuid_to_unregister):
        """
        Unregisters a UUID. Publishes SUCCESS/FAILURE for the unregistration command.
        If the unregistered item had a pending registration, it's marked as FAILURE.
        """
        original_cmd_uuid_for_unregister = uuid_to_unregister # Assuming unregister command Uuid is the item Uuid

        # Case 1: Command to unregister is currently being actively processed.
        if self.is_processing and uuid_to_unregister == self.current_processing_uuid:
            self.interruption_requested_for_uuid[uuid_to_unregister] = True
            interrupt_event = self.processing_events.get(uuid_to_unregister)
            if interrupt_event:
                interrupt_event.set()
            
            # The execute_command will handle its FAILURE.
            # The unregistration command itself is successful in initiating the stop.
            self._publish_command_status(self.unregister_topic, original_cmd_uuid_for_unregister, "SUCCESS")
            # State transitions (COMPLETING, RESETTING) will be managed by execute_command's completion
            # and subsequent state logic.
            if uuid_to_unregister in self.pending_registrations: # Should not happen if processing, but as safeguard
                reg_cmd_uuid = self.pending_registrations.pop(uuid_to_unregister)
                self._publish_command_status(self.register_topic, reg_cmd_uuid, "FAILURE") # Reason: Interrupted


            self.uuids.pop(0) # Remove from queue

            if not self.uuids: # Queue is now empty
                self.transition_to(PackMLState.COMPLETING, "#") # Signal to go to IDLE
            else: # More items in queue
                self.transition_to(PackMLState.STARTING)
            

        # Case 2: Command is at head of queue AND not currently processing.
        elif self.uuids and uuid_to_unregister == self.uuids[0] and not self.is_processing:
            removed_uuid = self.uuids.pop(0)
            self._publish_command_status(self.unregister_topic, original_cmd_uuid_for_unregister, "SUCCESS")
            if removed_uuid in self.pending_registrations:
                reg_cmd_uuid = self.pending_registrations.pop(removed_uuid)
                self._publish_command_status(self.register_topic, reg_cmd_uuid, "FAILURE") # Reason: Unregistered before processing start
            
            self.publish_state()
            if not self.uuids: # Queue is now empty
                self.transition_to(PackMLState.COMPLETING, "#") # Signal to go to IDLE
            else: # More items in queue
                self.transition_to(PackMLState.STARTING)


        # Case 3: Command is in queue, but not at the head.
        elif uuid_to_unregister in self.uuids:
            self.uuids.remove(uuid_to_unregister)
            self._publish_command_status(self.unregister_topic, original_cmd_uuid_for_unregister, "SUCCESS")
            if uuid_to_unregister in self.pending_registrations:
                reg_cmd_uuid = self.pending_registrations.pop(uuid_to_unregister)
                self._publish_command_status(self.register_topic, reg_cmd_uuid, "FAILURE") # Reason: Unregistered before processing start
            
            self.publish_state()
            # If the machine was in EXECUTE and the queue becomes empty (should not happen if not head),
            # or if it was IDLE and an item was removed.
            if not self.uuids and self.state not in [PackMLState.IDLE, PackMLState.RESETTING, PackMLState.COMPLETING, PackMLState.COMPLETE]:
                 self.transition_to(PackMLState.COMPLETING, "#")


        # Case 4: UUID not found in active processing or queue.
        else:
            self._publish_command_status(self.unregister_topic, original_cmd_uuid_for_unregister, "FAILURE") # Reason: Not found
            print(f"Unregistration failed for {uuid_to_unregister}: Not found.")
            return # No further state changes if not found

        # Check if queue is empty and initiate shutdown if not already in a terminal/transient state
        if not self.uuids and not self.is_processing and \
           self.state not in [PackMLState.IDLE, PackMLState.RESETTING, PackMLState.COMPLETING, PackMLState.COMPLETE, PackMLState.STOPPED, PackMLState.ABORTED]:
            self.transition_to(PackMLState.COMPLETING, "#") # Use "#" to signify a general clear down

    def _handle_process_completion(self, completed_uuid, final_command_state, execute_topic: Topic):
        """Handles post-processing after a command's process_function finishes or fails."""
        # Publish final command status
        timestamp_final = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
        response_final = {
            "State": final_command_state,
            "TimeStamp": timestamp_final,
            "Uuid": completed_uuid
        }
        execute_topic.publish(response_final, self.client, False)

        # Cleanup processing-specific attributes
        # Note: self.is_processing and self.current_processing_uuid are reset by completing_state
        if completed_uuid in self.processing_events:
            del self.processing_events[completed_uuid]
        if completed_uuid in self.interruption_requested_for_uuid:
            del self.interruption_requested_for_uuid[completed_uuid]
        
        self.is_processing = False # Reset processing flag


    def abort_command(self): # External command to trigger "stop current task and clear queue"
        """Attempts to stop the current process, clears the queue, and transitions to ABORTED."""
        print("Abort command received.")
        
        # Attempt to interrupt the currently active process
        if self.is_processing and self.current_processing_uuid:
            active_uuid = self.current_processing_uuid
            print(f"Attempting to interrupt active process for abort: {active_uuid}")
            self.interruption_requested_for_uuid[active_uuid] = True # Mark for failure
            interrupt_event = self.processing_events.get(active_uuid)
            if interrupt_event:
                interrupt_event.set()
        
        uuid_being_processed = self.current_processing_uuid if self.is_processing else "#"
        self.transition_to(PackMLState.ABORTING, uuid_being_processed)


    def execute_command(self, message, execute_topic:Topic, process_function, *args):
        if self.state == PackMLState.EXECUTE:
            if self.uuids and message.get("Uuid") == self.uuids[0] and not self.is_processing:
                active_uuid = self.uuids[0] # Do not pop from self.uuids here; completing_state will.
                
                self.current_processing_uuid = active_uuid
                self.interruption_requested_for_uuid[active_uuid] = False 
                
                interrupt_event = threading.Event()
                can_be_interrupted_immediately = False
                
                try:
                    sig = inspect.signature(process_function)
                    if 'interrupt_event' in sig.parameters:
                        can_be_interrupted_immediately = True
                except ValueError: # Handles built-ins or other non-introspectable callables
                    pass 

                if can_be_interrupted_immediately:
                    self.processing_events[active_uuid] = interrupt_event

                timestamp_running = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
                response_running = {
                    "State": "RUNNING",
                    "TimeStamp": timestamp_running,
                    "Uuid": active_uuid
                }
                execute_topic.publish(response_running, self.client, False)
                
                self.is_processing = True # Set flag before starting thread
                
                def process_wrapper_thread_target(
                    current_self, 
                    uuid_for_thread, 
                    topic_for_thread, 
                    func_for_thread, 
                    can_interrupt, 
                    event_for_thread, 
                    *process_func_args):
                    """Target function for the processing thread."""
                    final_state_thread = "SUCCESSFUL"
                    try:
                        if can_interrupt:
                            func_for_thread(event_for_thread, *process_func_args)
                        else:
                            func_for_thread(*process_func_args)
                        
                        # Check if interruption was requested externally during non-interruptible execution
                        # or if an interruptible function completed but was still marked for interruption.
                        if current_self.interruption_requested_for_uuid.get(uuid_for_thread, False):
                            final_state_thread = "FAILURE"
                            print(f"Process for {uuid_for_thread} was marked as interrupted.")

                    except Exception as e:
                        print(f"Exception in process_function thread for {uuid_for_thread}: {e}")
                        final_state_thread = "FAILURE"
                    finally:
                        # This ensures completion handling occurs even if process_function errors out.
                        current_self._handle_process_completion(uuid_for_thread, final_state_thread, topic_for_thread)

                processing_thread = threading.Thread(
                    target=process_wrapper_thread_target,
                    args=(self, active_uuid, execute_topic, process_function, can_be_interrupted_immediately, interrupt_event, *args),
                    name=f"ProcessThread-{active_uuid}"
                )
                processing_thread.daemon = True # Allows main program to exit even if thread is running
                processing_thread.start()
                # Note: We DO NOT call processing_thread.join() here to keep execute_command non-blocking.

            else: # Conditions for execution not met
                attempted_uuid = message.get("Uuid") if message else "UNKNOWN_MESSAGE_UUID"
                current_queue_head = self.uuids[0] if self.uuids else "EMPTY_QUEUE"
                print(f"Execute command rejected for UUID '{attempted_uuid}'. "
                      f"Current State: {self.state.value}, Expected Head: '{current_queue_head}', "
                      f"Is Processing: {self.is_processing}, Queue: {self.uuids}")
                
                timestamp_failure = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
                response_failure = {
                    "State": "FAILURE",
                    "TimeStamp": timestamp_failure,
                    "Uuid": attempted_uuid 
                }
                execute_topic.publish(response_failure, self.client, False)
        else: # Not in EXECUTE state
            attempted_uuid = message.get("Uuid") if message else "UNKNOWN_MESSAGE_UUID"
            print(f"Execute command rejected for UUID '{attempted_uuid}'. Machine not in EXECUTE state (current: {self.state.value}).")
            timestamp_failure = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
            response_failure = {
                "State": "FAILURE",
                "TimeStamp": timestamp_failure,
                "Uuid": attempted_uuid
            }
            execute_topic.publish(response_failure, self.client, False)


    def idle_state(self):
        self.Uuid = None
        self.current_processing_uuid = None
        self.is_processing = False
        if self.uuids:
            self.transition_to(PackMLState.STARTING)

    def starting_state(self):
        if not self.uuids:
            self.transition_to(PackMLState.IDLE)
            return

        self.Uuid = self.uuids[0]
        if self.Uuid in self.pending_registrations:
            original_reg_cmd_uuid = self.pending_registrations.pop(self.Uuid)
            self._publish_command_status(self.register_topic, original_reg_cmd_uuid, "SUCCESS")
            
        self.transition_to(PackMLState.EXECUTE)

    def completing_state(self, uuid_completed):
        if uuid_completed == "#":
            self.uuids.clear()
        elif uuid_completed in self.uuids:
            try:
                self.uuids.pop(0)
            except IndexError:
                print(f"Warning: Tried to pop from empty uuids list in completing_state for {uuid_completed}")

        if self.current_processing_uuid == uuid_completed:
            self.current_processing_uuid = None
            self.is_processing = False 

        self.Uuid = None
        self.publish_state()
        self.transition_to(PackMLState.COMPLETE)        
        
    def aborting_state(self, aborted_task_uuid):
        """State entered when an abort is initiated."""
        print(f"Entering ABORTING state. Task (if any) that was active: {aborted_task_uuid}")
        
        for uuid, reg_cmd_uuid in list(self.pending_registrations.items()):
            self._publish_command_status(self.register_topic, reg_cmd_uuid, "FAILURE")
        self.pending_registrations.clear()

        self.uuids.clear()
        self.Uuid = None 
        self.current_processing_uuid = None 
        self.is_processing = False

        self.publish_state()
        self.transition_to(PackMLState.ABORTED)

    def resetting_state(self):
        self.Uuid = None
        self.current_processing_uuid = None
        self.is_processing = False


        self.transition_to(PackMLState.IDLE)

    def clearing_state(self):
        self.transition_to(PackMLState.STOPPED)
        self.uuids.clear()

    def transition_to(self, new_state, uuid_param=None):  
        """Transition to a new state and publish it"""
        self.state = new_state
        self.publish_state()

        if new_state == PackMLState.IDLE:
            self.idle_state()
        elif new_state == PackMLState.STARTING:
            if self.uuids:
                self.starting_state()
        elif new_state == PackMLState.COMPLETING:
            self.completing_state(uuid_param)
        elif new_state == PackMLState.COMPLETE:
            self.transition_to(PackMLState.RESETTING)
        elif new_state == PackMLState.RESETTING:
            self.resetting_state()
        elif new_state == PackMLState.ABORTING:
            self.aborting_state(uuid_param)
        elif new_state == PackMLState.CLEARING:
            self.clearing_state() # Renamed from self.clearing() for consistency

    def publish_state(self):
        """Publish the current state"""
        response = {
            "State": self.state.value,
            "TimeStamp": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z'),
            "ProcessQueue": self.uuids
        }
        self.state_topic.publish(response, self.client, True)