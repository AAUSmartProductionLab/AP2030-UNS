import enum
import datetime
import threading  # Add this import
import inspect   # Add this import
import os        # Add this import for file path handling
from typing import Optional
from MQTT_classes import Proxy, Publisher, ResponseAsync, Topic


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
    def __init__(self,  base_topic, client: Proxy, properties, config_path: Optional[str] = None, custom_handlers=None, enable_occupation: bool = True, auto_execute: bool = False):
        self.state = PackMLState.IDLE
        self.base_topic = base_topic
        # Keep if used elsewhere, otherwise consider removing
        self.running_execution = False
        # Mqtt stuff
        self.client = client
        self.properties = properties
        self.Uuid = None
        
        self.custom_handlers = custom_handlers or {}
        self.enable_occupation = enable_occupation
        self.auto_execute = auto_execute

        # YAML config path for registration
        self.config_path = config_path

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

        # Occupation topics (optional - can be disabled for services like planners)
        self.register_topic = None
        self.unregister_topic = None
        
        if self.enable_occupation:
            self.register_topic = ResponseAsync(
                self.base_topic+"/DATA/Occupy",
                self.base_topic+"/CMD/Occupy",
                "./MQTTSchemas/commandResponse.schema.json",
                "./MQTTSchemas/command.schema.json",
                2,
                self.register_callback
            )
            self.unregister_topic = ResponseAsync(
                self.base_topic+"/DATA/Release",
                self.base_topic+"/CMD/Release",
                "./MQTTSchemas/commandResponse.schema.json",
                "./MQTTSchemas/command.schema.json",
                2,
                self.unregister_callback
            )
        
        # Command topic for manual state control (Start, Stop, Reset, etc.)
        from MQTT_classes import Subscriber
        self.command_topic = Subscriber(
            self.base_topic + "/CMD/State",
            "./MQTTSchemas/stateCommand.schema.json",
            2,
            self.state_command_callback
        )

        self.state_topic = Publisher(
            self.base_topic+"/DATA/State",
            "./MQTTSchemas/stationState.schema.json",
            2
        )
        
        # Build list of topics to register
        topics = [self.command_topic, self.state_topic]
        if self.enable_occupation:
            topics.extend([self.register_topic, self.unregister_topic])
        for topic in topics:
            client.register_topic(topic)

        self.publish_state()
        
        # Auto-transition to EXECUTE for service-type stations (no occupation needed)
        if self.auto_execute:
            self.state = PackMLState.EXECUTE
            self.publish_state()
            print(f"PackML: Auto-started in EXECUTE state (service mode)")

    def state_command_callback(self, topic, client, message, properties):
        """Callback for external state commands like Start, Stop, Reset."""
        state_id = message.get("StateId")
        if not state_id:
            # Fallback to ButtonId for backward compatibility
            state_id = message.get("ButtonId")
        if not state_id:
            print(f"PackML: Received state command without StateId or ButtonId: {message}")
            return
            
        cmd = str(state_id).lower()
        print(f"PackML State Command received: {state_id} (Current State: {self.state.value})")

        if cmd == "start":
            if self.state == PackMLState.IDLE:
                self.transition_to(PackMLState.STARTING)
        
        elif cmd == "stop":
            if self.state not in [PackMLState.STOPPED, PackMLState.STOPPING, PackMLState.ABORTED, PackMLState.ABORTING]:
                self.transition_to(PackMLState.STOPPING)
                
        elif cmd == "hold":
            if self.state == PackMLState.EXECUTE:
                self.transition_to(PackMLState.HOLDING)
                
        elif cmd == "unhold":
            if self.state in [PackMLState.HELD, PackMLState.HOLDING]:
                self.transition_to(PackMLState.UNHOLDING)
        
        elif cmd == "clear":
            if self.state == PackMLState.ABORTED:
                self.transition_to(PackMLState.CLEARING)

        elif cmd == "reset":
            if self.state in [PackMLState.STOPPED, PackMLState.ABORTED, PackMLState.COMPLETE]:
                self.transition_to(PackMLState.RESETTING)
        
        elif cmd == "suspend":
            if self.state == PackMLState.EXECUTE:
                self.transition_to(PackMLState.SUSPENDING)
                
        elif cmd == "unsuspend":
            if self.state in [PackMLState.SUSPENDED, PackMLState.SUSPENDING]:
                self.transition_to(PackMLState.UNSUSPENDING)
        
        elif cmd == "abort":
            if self.state not in [PackMLState.ABORTED, PackMLState.ABORTING]:
                self.abort_command()

    def _publish_command_status(self, status_topic_publisher, command_uuid, state_value):
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat(
            timespec='milliseconds').replace('+00:00', 'Z')
        response = {
            "State": state_value,
            "TimeStamp": timestamp,
            "Uuid": command_uuid
        }
        status_topic_publisher.publish(response, self.client, False)

    def register_callback(self, topic, client, message, properties):
        """Callback handler for registering commands."""
        try:
            # This is the UUID of the item to be queued
            command_uuid = message.get("Uuid")
            if not command_uuid:
                print("Error in register_callback: Message missing Uuid.")
                # Optionally publish a generic error if possible, or log
                return

            # Publish RUNNING for the registration command itself
            self._publish_command_status(
                self.register_topic, command_uuid, "RUNNING")
            self.register_command(command_uuid)  # Pass the UUID to be queued

        except Exception as e:
            print(f"Error in register_callback: {e}")
            # If command_uuid was parsed, publish FAILURE for it
            if 'command_uuid' in locals() and command_uuid:
                self._publish_command_status(
                    self.register_topic, command_uuid, "FAILURE")

    def unregister_callback(self, topic, client, message, properties):
        """Callback handler for unregistering commands."""
        try:
            # This is the UUID of the item to be unregistered
            command_uuid = message.get("Uuid")
            if not command_uuid:
                print("Error in unregister_callback: Message missing Uuid.")
                return

            # Publish RUNNING for the unregistration command itself
            # Success/Failure will be published by unregister_command
            self._publish_command_status(
                self.unregister_topic, command_uuid, "RUNNING")
            # Pass the UUID to be unregistered
            self.unregister_command(command_uuid)

        except Exception as e:
            print(f"Error in unregister_callback: {e}")
            if 'command_uuid' in locals() and command_uuid:
                self._publish_command_status(
                    self.unregister_topic, command_uuid, "FAILURE")

    def register_command(self, uuid_to_queue):
        """
        Registers a UUID. The registration command itself is considered RUNNING
        until the item reaches the head of the queue (SUCCESS) or is removed/fails (FAILURE).
        """
        if uuid_to_queue in self.uuids or uuid_to_queue == self.current_processing_uuid:
            # Reason: Duplicate/Already active
            self._publish_command_status(
                self.register_topic, uuid_to_queue, "FAILURE")
            print(
                f"Registration failed for {uuid_to_queue}: Already registered or active.")
            return

        self.uuids.append(uuid_to_queue)
        # Map item UUID to its own command UUID for status
        self.pending_registrations[uuid_to_queue] = uuid_to_queue

        self.publish_state()  # Update observers about the new queue state

        if self.state == PackMLState.IDLE:  # If IDLE, and this is the first item
            self.transition_to(PackMLState.STARTING)
        # If not IDLE, or if other items were already queued, the RUNNING status persists.
        # starting_state will handle publishing SUCCESS when this uuid_to_queue reaches the front.

    def unregister_command(self, uuid_to_unregister):
        """
        Unregisters a UUID. Publishes SUCCESS/FAILURE for the unregistration command.
        If the unregistered item had a pending registration, it's marked as FAILURE.
        """
        original_cmd_uuid_for_unregister = uuid_to_unregister  # Assuming unregister command Uuid is the item Uuid

        # Case 1: Command to unregister is currently being actively processed.
        if self.is_processing and uuid_to_unregister == self.current_processing_uuid:
            self.interruption_requested_for_uuid[uuid_to_unregister] = True
            interrupt_event = self.processing_events.get(uuid_to_unregister)
            if interrupt_event:
                interrupt_event.set()

            # The execute_command will handle its FAILURE.
            # The unregistration command itself is successful in initiating the stop.
            self._publish_command_status(
                self.unregister_topic, original_cmd_uuid_for_unregister, "SUCCESS")
            # State transitions (COMPLETING, RESETTING) will be managed by execute_command's completion
            # and subsequent state logic.
            # Should not happen if processing, but as safeguard
            if uuid_to_unregister in self.pending_registrations:
                reg_cmd_uuid = self.pending_registrations.pop(
                    uuid_to_unregister)
                self._publish_command_status(
                    self.register_topic, reg_cmd_uuid, "FAILURE")  # Reason: Interrupted

            self.uuids.pop(0)  # Remove from queue

            if not self.uuids:  # Queue is now empty
                # Signal to go to IDLE
                self.transition_to(PackMLState.COMPLETING, "#")
            else:  # More items in queue
                self.transition_to(PackMLState.STARTING)

        # Case 2: Command is at head of queue AND not currently processing.
        elif self.uuids and uuid_to_unregister == self.uuids[0] and not self.is_processing:
            removed_uuid = self.uuids.pop(0)
            self._publish_command_status(
                self.unregister_topic, original_cmd_uuid_for_unregister, "SUCCESS")
            if removed_uuid in self.pending_registrations:
                reg_cmd_uuid = self.pending_registrations.pop(removed_uuid)
                # Reason: Unregistered before processing start
                self._publish_command_status(
                    self.register_topic, reg_cmd_uuid, "FAILURE")

            self.publish_state()
            if not self.uuids:  # Queue is now empty
                # Signal to go to IDLE
                self.transition_to(PackMLState.COMPLETING, "#")
            else:  # More items in queue
                self.transition_to(PackMLState.STARTING)

        # Case 3: Command is in queue, but not at the head.
        elif uuid_to_unregister in self.uuids:
            self.uuids.remove(uuid_to_unregister)
            self._publish_command_status(
                self.unregister_topic, original_cmd_uuid_for_unregister, "SUCCESS")
            if uuid_to_unregister in self.pending_registrations:
                reg_cmd_uuid = self.pending_registrations.pop(
                    uuid_to_unregister)
                # Reason: Unregistered before processing start
                self._publish_command_status(
                    self.register_topic, reg_cmd_uuid, "FAILURE")

            self.publish_state()
            # If the machine was in EXECUTE and the queue becomes empty (should not happen if not head),
            # or if it was IDLE and an item was removed.
            if not self.uuids and self.state not in [PackMLState.IDLE, PackMLState.RESETTING, PackMLState.COMPLETING, PackMLState.COMPLETE]:
                self.transition_to(PackMLState.COMPLETING, "#")

        # Case 4: UUID not found in active processing or queue.
        else:
            self._publish_command_status(
                self.unregister_topic, original_cmd_uuid_for_unregister, "FAILURE")  # Reason: Not found
            print(
                f"Unregistration failed for {uuid_to_unregister}: Not found.")
            return  # No further state changes if not found

        # Check if queue is empty and initiate shutdown if not already in a terminal/transient state
        if not self.uuids and not self.is_processing and \
           self.state not in [PackMLState.IDLE, PackMLState.RESETTING, PackMLState.COMPLETING, PackMLState.COMPLETE, PackMLState.STOPPED, PackMLState.ABORTED]:
            # Use "#" to signify a general clear down
            self.transition_to(PackMLState.COMPLETING, "#")

    def _handle_process_completion(self, completed_uuid, final_command_state, execute_topic: Topic, additional_response_data=None):
        """Handles post-processing after a command's process_function finishes or fails.
        
        Args:
            completed_uuid: UUID of the completed command
            final_command_state: "SUCCESS" or "FAILURE"
            execute_topic: Topic to publish response to
            additional_response_data: Optional dict with additional fields to include in response
        """
        # Publish final command status
        timestamp_final = datetime.datetime.now(datetime.timezone.utc).isoformat(
            timespec='milliseconds').replace('+00:00', 'Z')
        response_final = {
            "State": final_command_state,
            "TimeStamp": timestamp_final,
            "Uuid": completed_uuid
        }
        
        # Merge additional response data if provided (e.g., planning results)
        if additional_response_data and isinstance(additional_response_data, dict):
            # Override State from additional_response_data if present
            if 'State' in additional_response_data:
                response_final['State'] = additional_response_data['State']
                final_command_state = additional_response_data['State']
            # Merge other fields
            for key, value in additional_response_data.items():
                if key not in ['Uuid', 'TimeStamp']:  # Don't override these
                    response_final[key] = value
        
        execute_topic.publish(response_final, self.client, False)

        # Cleanup processing-specific attributes
        # Note: self.is_processing and self.current_processing_uuid are reset by completing_state
        if completed_uuid in self.processing_events:
            del self.processing_events[completed_uuid]
        if completed_uuid in self.interruption_requested_for_uuid:
            del self.interruption_requested_for_uuid[completed_uuid]

        self.is_processing = False  # Reset processing flag

    def abort_command(self):  # External command to trigger "stop current task and clear queue"
        """Attempts to stop the current process, clears the queue, and transitions to ABORTED."""
        print("Abort command received.")

        # Attempt to interrupt the currently active process
        if self.is_processing and self.current_processing_uuid:
            active_uuid = self.current_processing_uuid
            print(
                f"Attempting to interrupt active process for abort: {active_uuid}")
            # Mark for failure
            self.interruption_requested_for_uuid[active_uuid] = True
            interrupt_event = self.processing_events.get(active_uuid)
            if interrupt_event:
                interrupt_event.set()

        uuid_being_processed = self.current_processing_uuid if self.is_processing else "#"
        self.transition_to(PackMLState.ABORTING, uuid_being_processed)

    def execute_command(self, message, execute_topic: Topic, process_function, *args):
        if self.state == PackMLState.EXECUTE:
            if self.uuids and message.get("Uuid") == self.uuids[0] and not self.is_processing:
                # Do not pop from self.uuids here; completing_state will.
                active_uuid = self.uuids[0]

                self.current_processing_uuid = active_uuid
                self.interruption_requested_for_uuid[active_uuid] = False

                interrupt_event = threading.Event()
                can_be_interrupted_immediately = False

                try:
                    sig = inspect.signature(process_function)
                    if 'interrupt_event' in sig.parameters:
                        can_be_interrupted_immediately = True
                except ValueError:  # Handles built-ins or other non-introspectable callables
                    pass

                if can_be_interrupted_immediately:
                    self.processing_events[active_uuid] = interrupt_event

                timestamp_running = datetime.datetime.now(datetime.timezone.utc).isoformat(
                    timespec='milliseconds').replace('+00:00', 'Z')
                response_running = {
                    "State": "RUNNING",
                    "TimeStamp": timestamp_running,
                    "Uuid": active_uuid
                }
                execute_topic.publish(response_running, self.client, False)

                self.is_processing = True  # Set flag before starting thread

                def process_wrapper_thread_target(
                        current_self,
                        uuid_for_thread,
                        topic_for_thread,
                        func_for_thread,
                        can_interrupt,
                        event_for_thread,
                        *process_func_args):
                    """Target function for the processing thread."""
                    final_state_thread = "SUCCESS"
                    response_data = None  # Additional response data from process function
                    try:
                        if can_interrupt:
                            result = func_for_thread(event_for_thread,
                                            *process_func_args)
                        else:
                            result = func_for_thread(*process_func_args)
                        
                        # If the process function returns a dict, use it as additional response data
                        if isinstance(result, dict):
                            response_data = result
                            # Check if the result indicates failure
                            if result.get('State') == 'FAILURE':
                                final_state_thread = "FAILURE"
                            elif result.get('State') == 'SUCCESS':
                                final_state_thread = "SUCCESS"

                        # Check if interruption was requested externally during non-interruptible execution
                        # or if an interruptible function completed but was still marked for interruption.
                        if current_self.interruption_requested_for_uuid.get(uuid_for_thread, False):
                            final_state_thread = "FAILURE"
                            print(
                                f"Process for {uuid_for_thread} was marked as interrupted.")

                    except Exception as e:
                        print(
                            f"Exception in process_function thread for {uuid_for_thread}: {e}")
                        final_state_thread = "FAILURE"
                        response_data = {"ErrorMessage": str(e)}
                    finally:
                        # This ensures completion handling occurs even if process_function errors out.
                        current_self._handle_process_completion(
                            uuid_for_thread, final_state_thread, topic_for_thread, response_data)

                processing_thread = threading.Thread(
                    target=process_wrapper_thread_target,
                    args=(self, active_uuid, execute_topic, process_function,
                          can_be_interrupted_immediately, interrupt_event, *args),
                    name=f"ProcessThread-{active_uuid}"
                )
                # Allows main program to exit even if thread is running
                processing_thread.daemon = True
                processing_thread.start()
                # Note: We DO NOT call processing_thread.join() here to keep execute_command non-blocking.

            else:  # Conditions for execution not met
                attempted_uuid = message.get(
                    "Uuid") if message else "UNKNOWN_MESSAGE_UUID"
                current_queue_head = self.uuids[0] if self.uuids else "EMPTY_QUEUE"
                print(f"Execute command rejected for UUID '{attempted_uuid}'. "
                      f"Current State: {self.state.value}, Expected Head: '{current_queue_head}', "
                      f"Is Processing: {self.is_processing}, Queue: {self.uuids}")

                timestamp_failure = datetime.datetime.now(datetime.timezone.utc).isoformat(
                    timespec='milliseconds').replace('+00:00', 'Z')
                response_failure = {
                    "State": "FAILURE",
                    "TimeStamp": timestamp_failure,
                    "Uuid": attempted_uuid
                }
                execute_topic.publish(response_failure, self.client, False)
        else:  # Not in EXECUTE state
            attempted_uuid = message.get(
                "Uuid") if message else "UNKNOWN_MESSAGE_UUID"
            print(
                f"Execute command rejected for UUID '{attempted_uuid}'. Machine not in EXECUTE state (current: {self.state.value}).")
            timestamp_failure = datetime.datetime.now(datetime.timezone.utc).isoformat(
                timespec='milliseconds').replace('+00:00', 'Z')
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
        # Call custom handler
        if 'on_starting' in self.custom_handlers:
            self.custom_handlers['on_starting']()
            
        if not self.uuids:
            self.transition_to(PackMLState.IDLE)
            return

        self.Uuid = self.uuids[0]
        if self.Uuid in self.pending_registrations:
            original_reg_cmd_uuid = self.pending_registrations.pop(self.Uuid)
            self._publish_command_status(
                self.register_topic, original_reg_cmd_uuid, "SUCCESS")

        self.transition_to(PackMLState.EXECUTE)

    def stopping_state(self):
        if 'on_stopping' in self.custom_handlers:
            self.custom_handlers['on_stopping']()
        self.transition_to(PackMLState.STOPPED)

    def holding_state(self):
        if 'on_holding' in self.custom_handlers:
            self.custom_handlers['on_holding']()
        self.transition_to(PackMLState.HELD)

    def unholding_state(self):
        if 'on_unholding' in self.custom_handlers:
            self.custom_handlers['on_unholding']()
        self.transition_to(PackMLState.EXECUTE)

    def suspending_state(self):
        if 'on_suspending' in self.custom_handlers:
            self.custom_handlers['on_suspending']()
        self.transition_to(PackMLState.SUSPENDED)

    def unsuspending_state(self):
        if 'on_unsuspending' in self.custom_handlers:
            self.custom_handlers['on_unsuspending']()
        self.transition_to(PackMLState.EXECUTE)

    def completing_state(self, uuid_completed):
        if uuid_completed == "#":
            self.uuids.clear()
        elif uuid_completed in self.uuids:
            try:
                self.uuids.pop(0)
            except IndexError:
                print(
                    f"Warning: Tried to pop from empty uuids list in completing_state for {uuid_completed}")

        if self.current_processing_uuid == uuid_completed:
            self.current_processing_uuid = None
            self.is_processing = False

        self.Uuid = None
        self.publish_state()
        self.transition_to(PackMLState.COMPLETE)

    def aborting_state(self, aborted_task_uuid):
        """State entered when an abort is initiated."""
        print(
            f"Entering ABORTING state. Task (if any) that was active: {aborted_task_uuid}")

        for uuid, reg_cmd_uuid in list(self.pending_registrations.items()):
            self._publish_command_status(
                self.register_topic, reg_cmd_uuid, "FAILURE")
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
        elif new_state == PackMLState.STOPPING:
            self.stopping_state()
        elif new_state == PackMLState.HOLDING:
            self.holding_state()
        elif new_state == PackMLState.UNHOLDING:
            self.unholding_state()
        elif new_state == PackMLState.SUSPENDING:
            self.suspending_state()
        elif new_state == PackMLState.UNSUSPENDING:
            self.unsuspending_state()
        elif new_state == PackMLState.COMPLETING:
            self.completing_state(uuid_param)
        elif new_state == PackMLState.COMPLETE:
            self.transition_to(PackMLState.RESETTING)
        elif new_state == PackMLState.RESETTING:
            self.resetting_state()
        elif new_state == PackMLState.ABORTING:
            self.aborting_state(uuid_param)
        elif new_state == PackMLState.CLEARING:
            self.clearing_state()

    def publish_state(self):
        """Publish the current state"""
        response = {
            "State": self.state.value,
            "TimeStamp": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z'),
            "ProcessQueue": self.uuids
        }
        self.state_topic.publish(response, self.client, True)

    def register_asset(self):
        """
        Publish YAML config to Registration/Config topic for asset registration.

        The Registration Service will receive the raw YAML and generate
        the full AAS description server-side.
        """
        if not self.config_path:
            return False

        # Resolve config path - try multiple locations
        config_file = None
        possible_paths = []

        if os.path.isabs(self.config_path):
            possible_paths = [self.config_path]
        else:
            possible_paths = [
                self.config_path,
                os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "..", "AASDescriptions", "Resource", "configs", self.config_path),
                os.path.join("/app", "AASDescriptions", "Resource",
                             "configs", self.config_path),
                os.path.join("AASDescriptions", "Resource",
                             "configs", self.config_path),
            ]

        for path in possible_paths:
            if os.path.exists(path):
                config_file = path
                break

        if not config_file:
            print(
                f"[Registration] Config file not found: {self.config_path}", flush=True)
            return False

        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                yaml_content = f.read()

            registration_topic = "NN/Nybrovej/InnoLab/Registration/Config" #self.base_topic + "/Registration/Config"
            self.client.publish(registration_topic,
                                yaml_content, qos=2, retain=False)

            print(
                f"[Registration] Published {len(yaml_content)} bytes to {registration_topic}", flush=True)
            return True

        except Exception as e:
            print(f"[Registration] Error: {e}", flush=True)
            return False
            import traceback
            traceback.print_exc()
            return False
