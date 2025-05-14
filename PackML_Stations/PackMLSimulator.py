import enum
import datetime


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
        self.running_execution = False
        # Mqtt stuff
        self.client = client
        self.properties = properties
        self.Uuid = None
        self.failureChance = 0.00

        # ProcessQueue
        self.is_processing = False
        self.uuids = []  # Track all queued command UUIDs

        self.publish_state()


    def start_command(self,message):
        """Register a command without immediate processing"""
        uuid = message.get("Uuid")
        
        if uuid not in self.uuids:
            self.uuids.append(uuid)
        self.transition_to(self.state)

    def complete_command(self, message):
        """Unregister a command by removing it from the queue if not being processed"""
        uuid = message.get("Uuid")
        if (uuid == self.uuids[0] and self.is_processing==False) or (uuid == "#" and self.is_processing==False):
            self.transition_to(PackMLState.COMPLETING, uuid)
            self.transition_to(PackMLState.RESETTING)
        elif uuid != self.uuids[0]:
            self.uuids.remove(uuid)
            self.transition_to(PackMLState.EXECUTE)
        else:
            # Remain in execute if it was not valid
            self.transition_to(PackMLState.EXECUTE)

    def execute_command(self, message, execute_topic, process_function, *args):
        if self.state == PackMLState.EXECUTE:
            if len(self.uuids)>0 and message.get("Uuid") == self.uuids[0] and not self.is_processing:
                timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
                response = {
                    "State": "RUNNING",
                    "TimeStamp": timestamp,
                    "Uuid": self.uuids[0]
                }
                execute_topic.publish(response, self.client,  False)
                self.is_processing=True
                process_function(*args)
                self.is_processing=False
                timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
                response = {
                    "State": "SUCCESSFUL",
                    "TimeStamp": timestamp,
                    "Uuid": self.uuids[0]
                }
                execute_topic.publish(response, self.client,  False)
            else:
                self.is_processing=False
                timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
                response = {
                    "State": "FAILURE",
                    "TimeStamp": timestamp,
                    "Uuid": self.uuids[0]
                }
                execute_topic.publish(response, self.client, False)

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

    def resetting_state(self):
        self.Uuid = None
        self.transition_to(PackMLState.IDLE)

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

    def publish_state(self):
        """Publish the current state"""
        response = {
            "State": self.state.value,
            "TimeStamp": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z'),
            "ProcessQueue": self.uuids
        }
        self.state_topic.publish(response, self.client, True)