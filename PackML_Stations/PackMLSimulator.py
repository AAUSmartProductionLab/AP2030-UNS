import random
import enum
import threading
import time
import queue
import datetime  # Importing datetime module


# Custom exceptions for PackML state transitions
class HoldException(Exception): pass
class SuspendException(Exception): pass
class AbortException(Exception): pass
class StopException(Exception): pass

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
    def __init__(self,  state_topic, start_topic,complete_topic,client, properties):
        self.state = PackMLState.IDLE
        self.state_topic = state_topic
        self.running_execution = False
        # Mqtt stuff
        self.client = client
        self.properties = properties
        self.Uuid = None
        self.failureChance = 0.00

        self.start_topic = start_topic
        self.complete_topic = complete_topic

        # ProcessQueue
        self.is_processing = False
        self.uuids = []  # Track all queued command UUIDs

        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
        response = {
            "State": "IDLE",
            "ProcessQueue": [],
            "TimeStamp": timestamp
        }
            
        self.state_topic.publish(response, self.client, True)


    def start_command(self,message):
        """Register a command without immediate processing"""
        uuid = message.get("Uuid")
        
        if uuid not in self.uuids:
            self.uuids.append(uuid)
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
        response = {
            "State": "RUNNING",
            "TimeStamp": timestamp,
            "Uuid": uuid
        }
        self.start_topic.publish(response, self.client,  False)
        self.transition_to(PackMLState.IDLE)

    def execute_command(self, message, execute_topic, process_function, *args):
        uuid = message.get("Uuid")
        if len(self.uuids)>0 and uuid == self.uuids[0] and self.state == PackMLState.EXECUTE and not self.is_processing:
            timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
            response = {
                "State": "RUNNING",
                "TimeStamp": timestamp,
                "Uuid": uuid
            }
            execute_topic.publish(response, self.client,  False)
            self.is_processing=True
            process_function(*args)
            self.is_processing=False
            timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
            response = {
                "State": "SUCCESSFUL",
                "TimeStamp": timestamp,
                "Uuid": uuid
            }
            execute_topic.publish(response, self.client,  False)
        else:
            self.is_processing=False
            timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
            response = {
                "State": "FAILURE",
                "TimeStamp": timestamp,
                "Uuid": uuid
            }
            execute_topic.publish(response, self.client, False)

    def complete_command(self, message):
        """Unregister a command by removing it from the queue if not being processed"""
        uuid = message.get("Uuid")
        response={}
        # Check if the command exists and is not currently being processed
        if uuid in self.uuids and ((uuid == self.uuids[0] and self.is_processing==False) or uuid != self.uuids[0]):
            self.transition_to(PackMLState.COMPLETING, uuid)
        else:
            timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
            response = {
                "State": "FAILURE",
                "TimeStamp": timestamp,
                "Uuid": uuid
            }
            self.complete_topic.publish(response, self.client, False)

    def idle_state(self):
        if self.uuids and len(self.uuids) > 0:
            self.transition_to(PackMLState.STARTING)

    def starting_state(self):
        self.Uuid = self.uuids[0]
        response={}
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
        response = {
            "State": "SUCCESSFUL",
            "TimeStamp": timestamp,
            "Uuid": self.Uuid 
        }
        self.start_topic.publish(response, self.client, False)
        self.transition_to(PackMLState.EXECUTE)

    def completing_state(self, uuid):
        self.uuids.remove(uuid)
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
        response = {
            "State": "SUCCESSFUL",
            "TimeStamp": timestamp,
            "Uuid": uuid
        }
        self.complete_topic.publish(response, self.client, False)
        self.transition_to(PackMLState.COMPLETE)

    def complete_state(self):
        self.transition_to(PackMLState.RESETTING)

    def resetting_state(self):
        self.Uuid = None
        self.transition_to(PackMLState.IDLE)

    def transition_to(self, new_state, uuid=None):  
        """Transition to a new state and publish it"""
        self.state = new_state
        # report the state change
        queued_uuids = self.uuids.copy()
        response = {
            "State": new_state.value,
            "TimeStamp": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z'),
            "ProcessQueue": queued_uuids if queued_uuids else []
        }
        self.state_topic.publish(response, self.client, True)

        if new_state == PackMLState.IDLE:
            self.idle_state()
        elif new_state == PackMLState.STARTING:
            self.starting_state()
        elif new_state == PackMLState.COMPLETING:
            self.completing_state(uuid)
        elif new_state == PackMLState.COMPLETE:
            self.complete_state()
        elif new_state == PackMLState.RESETTING:
            self.resetting_state()
