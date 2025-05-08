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
        self.CommandUuid = None
        self.failureChance = 0.00

        self.start_topic = start_topic
        self.complete_topic = complete_topic

        # ProcessQueue
        self.is_processing = False
        self.command_uuids = []  # Track all queued command UUIDs

        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
        response = {
            "State": "IDLE",
            "ProcessQueue": [],
            "TimeStamp": timestamp
        }
            
        self.state_topic.publish(response, self.client, True)


    def start_command(self,message):
        """Register a command without immediate processing"""
        command_uuid = message.get("CommandUuid")
        
        if command_uuid not in self.command_uuids:
            self.command_uuids.append(command_uuid)
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
        response = {
            "State": "RUNNING",
            "TimeStamp": timestamp,
            "CommandUuid": command_uuid
        }
        self.start_topic.publish(response, self.client,  False)
        self.transition_to(PackMLState.IDLE)

    def execute_command(self, message, execute_topic, process_function, *args):
        command_uuid = message.get("CommandUuid")
        if len(self.command_uuids)>0 and command_uuid == self.command_uuids[0] and self.state == PackMLState.EXECUTE and not self.is_processing:
            timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
            response = {
                "State": "RUNNING",
                "TimeStamp": timestamp,
                "CommandUuid": command_uuid
            }
            execute_topic.publish(response, self.client,  False)
            self.is_processing=True
            process_function(*args)
            self.is_processing=False
            timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
            response = {
                "State": "SUCCESSFUL",
                "TimeStamp": timestamp,
                "CommandUuid": command_uuid
            }
            execute_topic.publish(response, self.client,  False)
        else:
            self.is_processing=False
            timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
            response = {
                "State": "FAILURE",
                "TimeStamp": timestamp,
                "CommandUuid": command_uuid
            }
            execute_topic.publish(response, self.client, False)

    def complete_command(self, message):
        """Unregister a command by removing it from the queue if not being processed"""
        command_uuid = message.get("CommandUuid")
        response={}
        # Check if the command exists and is not currently being processed
        if command_uuid in self.command_uuids and ((command_uuid == self.command_uuids[0] and self.is_processing==False) or command_uuid != self.command_uuids[0]):
            self.transition_to(PackMLState.COMPLETING, command_uuid)
        else:
            timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
            response = {
                "State": "FAILURE",
                "TimeStamp": timestamp,
                "CommandUuid": command_uuid
            }
            self.complete_topic.publish(response, self.client, False)

    def idle_state(self):
        if self.command_uuids and len(self.command_uuids) > 0:
            self.transition_to(PackMLState.STARTING)

    def starting_state(self):
        self.CommandUuid = self.command_uuids[0]
        response={}
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
        response = {
            "State": "SUCCESSFUL",
            "TimeStamp": timestamp,
            "CommandUuid": self.CommandUuid 
        }
        self.start_topic.publish(response, self.client, False)
        self.transition_to(PackMLState.EXECUTE)

    def completing_state(self, command_uuid):
        self.command_uuids.remove(command_uuid)
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
        response = {
            "State": "SUCCESSFUL",
            "TimeStamp": timestamp,
            "CommandUuid": command_uuid
        }
        self.complete_topic.publish(response, self.client, False)
        self.transition_to(PackMLState.COMPLETE)

    def complete_state(self):
        self.transition_to(PackMLState.RESETTING)

    def resetting_state(self):
        self.CommandUuid = None
        self.transition_to(PackMLState.IDLE)

    def transition_to(self, new_state, command_uuid=None):  
        """Transition to a new state and publish it"""
        self.state = new_state
        # report the state change
        queued_uuids = self.command_uuids.copy()
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
            self.completing_state(command_uuid)
        elif new_state == PackMLState.COMPLETE:
            self.complete_state()
        elif new_state == PackMLState.RESETTING:
            self.resetting_state()
