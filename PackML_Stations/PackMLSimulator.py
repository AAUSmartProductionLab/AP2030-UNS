import enum
import datetime
import threading # Add this import
import inspect   # Add this import


# # Custom exceptions for PackML state transitions
# class HoldException(Exception): pass
# class SuspendException(Exception): pass
# class AbortException(Exception): pass
# class StopException(Exception): pass

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
    def __init__(self,  state_topic, client, properties):
        self.state = PackMLState.IDLE
        self.state_topic = state_topic
        self.running_execution = False # Keep if used elsewhere, otherwise consider removing
        # Mqtt stuff
        self.client = client
        self.properties = properties
        self.Uuid = None # Managed by starting_state/resetting_state
        self.failureChance = 0.00 # Keep if used

        # ProcessQueue
        self.is_processing = False
        self.uuids = []  # Track all queued command UUIDs
        
        self.current_processing_uuid = None     # UUID of the command currently in process_function
        self.processing_events = {} # Stores threading.Event for interruptible processes
        self.interruption_requested_for_uuid = {} # Tracks if complete was called for a UUID during its processing

        self.publish_state()


    def start_command(self,message):
        """Register a command without immediate processing"""
        uuid = message.get("Uuid")
        
        if uuid not in self.uuids:
            self.uuids.append(uuid)
        self.transition_to(self.state)

    def complete_command(self, message):
        """Unregister a command. If it's processing, flag for failure and attempt immediate stop if supported."""
        uuid_to_complete = message.get("Uuid")
        
        if not uuid_to_complete or not self.uuids:
            return

        # Case 1: Command to complete is the one currently being actively processed.
        if self.is_processing and uuid_to_complete == self.current_processing_uuid:
            # Mark that an interruption was requested for this command.
            self.interruption_requested_for_uuid[uuid_to_complete] = True
            
            # Attempt to signal immediate stop if the process_function supports it.
            interrupt_event = self.processing_events.get(uuid_to_complete)
            if interrupt_event:
                interrupt_event.set() 
            
            # Proceed with normal completion state transitions.
            # execute_command will handle publishing FAILURE based on interruption_requested_for_uuid.
            self.transition_to(PackMLState.COMPLETING, uuid_to_complete)
            self.transition_to(PackMLState.RESETTING)

        # Case 2: Command is at head of queue AND not currently processing.
        elif self.uuids and uuid_to_complete == self.uuids[0] and not self.is_processing:
            self.transition_to(PackMLState.COMPLETING, uuid_to_complete)
            self.transition_to(PackMLState.RESETTING)
        
        # Case 3: Command is in queue, but not at the head (and thus not processing).
        elif uuid_to_complete in self.uuids and (not self.uuids or uuid_to_complete != self.uuids[0]):
            self.uuids.remove(uuid_to_complete) 
            self.publish_state() 
            if self.state == PackMLState.EXECUTE:
                 self.transition_to(PackMLState.EXECUTE)
        
        # Case 4: Fallback
        else:
            if self.state == PackMLState.EXECUTE and self.uuids:
                self.transition_to(PackMLState.EXECUTE)


    def abort_command(self):
        self.transition_to(PackMLState.ABORTING)
        self.transition_to(PackMLState.CLEARING)
        self.transition_to(PackMLState.RESETTING)

    def execute_command(self, message, execute_topic, process_function, *args):
        if self.state == PackMLState.EXECUTE:
            if self.uuids and message.get("Uuid") == self.uuids[0] and not self.is_processing:
                
                active_uuid = self.uuids[0]
                self.current_processing_uuid = active_uuid
                # Reset/initialize interruption flag for this specific command execution
                self.interruption_requested_for_uuid[active_uuid] = False 
                
                interrupt_event = threading.Event()
                can_be_interrupted_immediately = False
                
                # Check if process_function is designed to accept an interrupt_event
                try:
                    sig = inspect.signature(process_function)
                    if 'interrupt_event' in sig.parameters:
                        can_be_interrupted_immediately = True
                except ValueError: # Handles built-ins or other non-introspectable callables
                    pass # Assume it cannot be interrupted immediately

                if can_be_interrupted_immediately:
                    self.processing_events[active_uuid] = interrupt_event

                timestamp_running = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
                response_running = {
                    "State": "RUNNING",
                    "TimeStamp": timestamp_running,
                    "Uuid": active_uuid
                }
                execute_topic.publish(response_running, self.client, False)
                
                self.is_processing = True
                
                def process_wrapper():
                    try:
                        if can_be_interrupted_immediately:
                            # Pass the event if the function expects it
                            process_function(interrupt_event, *args)
                        else:
                            # Call normally if it doesn't expect the event
                            process_function(*args)
                    except Exception as e:
                        print(f"Exception in process_function thread for {active_uuid}: {e}")
                        # Optionally, flag for failure if process_function itself errors out
                        self.interruption_requested_for_uuid[active_uuid] = True


                processing_thread = threading.Thread(target=process_wrapper, name=f"ProcessThread-{active_uuid}")
                processing_thread.start()
                processing_thread.join()

                self.is_processing = False
                
                final_command_state = "SUCCESSFUL"
                # Check if an interruption was requested (e.g., by complete_command) during execution
                if self.interruption_requested_for_uuid.get(active_uuid, False):
                    final_command_state = "FAILURE"
                
                timestamp_final = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
                response_final = {
                    "State": final_command_state,
                    "TimeStamp": timestamp_final,
                    "Uuid": active_uuid
                }
                execute_topic.publish(response_final, self.client, False)

                # Cleanup
                if active_uuid in self.processing_events:
                    del self.processing_events[active_uuid]
                if active_uuid in self.interruption_requested_for_uuid:
                    del self.interruption_requested_for_uuid[active_uuid]
                self.current_processing_uuid = None

            else:
                attempted_uuid = message.get("Uuid") if message else "UNKNOWN_MESSAGE_UUID"
                timestamp_failure = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
                response_failure = {
                    "State": "FAILURE",
                    "TimeStamp": timestamp_failure,
                    "Uuid": attempted_uuid 
                }
                execute_topic.publish(response_failure, self.client, False)

    def idle_state(self):
        #Start the next process if there ary any that registered themselves with the start command
        if self.uuids and len(self.uuids) > 0:
            self.transition_to(PackMLState.STARTING)

    def starting_state(self):
        self.Uuid = self.uuids[0]
        self.transition_to(PackMLState.EXECUTE)

    def completing_state(self, uuid):
        self.transition_to(PackMLState.COMPLETE)        
        if uuid=="#":
            self.uuids.clear()
        else:
            self.uuids.remove(uuid)

    def aborting_state(self, uuid):
        self.transition_to(PackMLState.ABORTED)        
        self.uuids.remove(uuid)

    def resetting_state(self):
        self.Uuid = None
        self.transition_to(PackMLState.IDLE)

    def clearing_state(self):
        self.transition_to(PackMLState.STOPPED)
        self.uuids.clear()

    def transition_to(self, new_state, uuid=None):  
        """Transition to a new state and publish it"""
        self.state = new_state
        # report the state change
        self.publish_state()

        if new_state == PackMLState.IDLE:
            self.idle_state()
        elif new_state == PackMLState.STARTING:
            self.starting_state()
        elif new_state == PackMLState.COMPLETING:
            self.completing_state(uuid)
        elif new_state == PackMLState.RESETTING:
            self.resetting_state()
        elif new_state == PackMLState.ABORTING:
            self.aborting_state(uuid)
        elif new_state == PackMLState.CLEARING:
            self.clearing()

    def publish_state(self):
        """Publish the current state"""
        response = {
            "State": self.state.value,
            "TimeStamp": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z'),
            "ProcessQueue": self.uuids
        }
        self.state_topic.publish(response, self.client, True)