import random
import enum
import threading
import time
import queue

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
    def __init__(self, register_topic,execute_topic, client, properties):
        self.state = PackMLState.IDLE
        self.register_topic = register_topic
        self.execute_topic = execute_topic
        self.client = client
        self.properties = properties
        self.CommandUuid = None
        self.publish_progress = None
        self.failureChance=0.01
        # Progress tracking
        self.total_duration = 0
        self.elapsed_time = 0
        self.progress = 0
        
        # Threading control
        self.progress_thread = None
        self.stop_progress = threading.Event()

        # ProcessQueue
        self.command_queue = queue.Queue()
        self.is_processing = False
        self.command_uuids = []  # Track all queued command UUIDs

    def register_command(self,message):
        """Register a command without immediate processing"""
        # Extract command UUID if available
        command_uuid = message.get("CommandUuid")
        
        # Just add the UUID to the tracking list without queueing for execution
        if command_uuid not in self.command_uuids:
            self.command_uuids.append(command_uuid)
        
        
        response = {
            "State": self.state.value,
            "ProcessQueue": self.command_uuids.copy()
        }
        self.register_topic.publish(response, self.client, self.properties)
        
        return command_uuid

    def process_next_command(self, message, process_function, duration=None, publish_progress=None):

        command_uuid = message.get("CommandUuid")

        if command_uuid and self.command_uuids and command_uuid == self.command_uuids[0]:
    
            # Extract command UUID if available
            self.CommandUuid = message.get("CommandUuid")
            self.publish_progress = publish_progress
            # Process the command
            self.run_state_machine(process_function, duration)

    def update_progress(self, progress_interval=0.1):
        """Background thread function to update and publish progress"""
        while not self.stop_progress.is_set():
            if self.state == PackMLState.EXECUTE and self.total_duration > 0:
                current_progress = min(self.elapsed_time / self.total_duration, 1.0)
                if current_progress != self.progress:
                    self.progress = current_progress
                    if self.publish_progress:
                        self.publish_progress(self)
            time.sleep(progress_interval)
    
    def start_progress_monitoring(self, progress_interval=0.1):
        """Start the progress monitoring thread"""
        self.stop_progress.clear()
        self.progress_thread = threading.Thread(
            target=self.update_progress,
            args=(progress_interval,),
            daemon=True
        )
        self.progress_thread.start()
    
    def stop_progress_monitoring(self):
        """Stop the progress monitoring thread"""
        if self.progress_thread and self.progress_thread.is_alive():
            self.stop_progress.set()
            self.progress_thread.join(timeout=0.5)
    
    def check_random_exceptions(self, in_execute=False):
        """Check for random exceptions based on state"""
        rand_val = random.random()
        
        # Common exceptions in any state
        if rand_val < self.failureChance:
            raise AbortException("Random abort occurred")
        elif rand_val < 2*self.failureChance:
            raise StopException("Random stop occurred")
        
        # Execute-specific exceptions
        if in_execute:
            if rand_val < 3*self.failureChance:
                raise HoldException("Random hold occurred")
            elif rand_val < 4*self.failureChance:
                raise SuspendException("Random suspend occurred")
    
    def transition_to(self, new_state, delay=0.1):
        """Transition to a new state and publish it"""
        self.state = new_state
        response = {"State": new_state.value}
        
        # Handle CommandUuid tracking
        if new_state in [PackMLState.IDLE, PackMLState.RESETTING]:
            # Clear current CommandUuid
            prev_uuid = self.CommandUuid
            self.CommandUuid = None
            self.publish_progress(self,reset=True)

            if prev_uuid and prev_uuid in self.command_uuids:
                self.command_uuids.remove(prev_uuid)
                
            # Get fresh queue state
            queued_uuids = self.command_uuids.copy()
            
            # For IDLE state with empty queue, use empty array
            response["ProcessQueue"] = queued_uuids if queued_uuids else []
        else:
            queued_uuids = self.command_uuids.copy()
            
            # Include current UUID if applicable
            if self.CommandUuid and self.CommandUuid not in queued_uuids:
                response["ProcessQueue"] = [self.CommandUuid] + queued_uuids
            else:
                response["ProcessQueue"] = queued_uuids
        
        self.execute_topic.publish(response, self.client, self.properties)

    
    def run_sequence(self, states, delay=0.1, check_exceptions=True):
        """Run a sequence of states with checks between each"""
        for state in states:
            self.transition_to(state, delay)
            if check_exceptions:
                        self.check_random_exceptions(in_execute=(state == PackMLState.EXECUTE))
    
    def execute_process_step(self, process_function, duration=2.0):
        """Execute a single step of the process with timing and progress tracking"""
        process_start = time.time()
        
        try:
            # Check for exceptions before starting
            self.check_random_exceptions(in_execute=True)
            
            # Adjust duration based on remaining time
            if self.total_duration:
                remaining_time = self.total_duration - self.elapsed_time
            
            # Execute the process
            result = process_function(min(duration, remaining_time),self)
            
            # Check for exceptions after completion
            self.check_random_exceptions(in_execute=True)
            
            return result
            
        except (HoldException, SuspendException) as e:
            # Track time before interruption
            if self.total_duration:
                process_time = time.time() - process_start
                self.elapsed_time += process_time
            raise e
    
    def handle_hold_sequence(self, process_function, **kwargs):
        """Handle the HOLD state sequence and return to EXECUTE"""
        self.run_sequence([PackMLState.HOLDING, PackMLState.HELD, PackMLState.UNHOLDING])
        self.transition_to(PackMLState.EXECUTE)
        return self.execute_process_step(process_function, **kwargs)
    
    def handle_suspend_sequence(self, process_function, **kwargs):
        """Handle the SUSPEND state sequence and return to EXECUTE"""
        self.run_sequence([PackMLState.SUSPENDING, PackMLState.SUSPENDED, PackMLState.UNSUSPENDING])
        self.transition_to(PackMLState.EXECUTE)
        return self.execute_process_step(process_function, **kwargs)
    
    def run_state_machine(self, process_function, max_duration=None, progress_interval=0.1, **kwargs):
        """Run the state machine with the given process function"""
        self.total_duration = max_duration
        self.elapsed_time = 0
        self.progress = 0
        result = None
        
        try:
            # Initial check and start sequence
            self.check_random_exceptions()
            self.transition_to(PackMLState.STARTING)
            self.check_random_exceptions()
            self.transition_to(PackMLState.EXECUTE, delay=0.0)
            
            # Start progress monitoring
            self.start_progress_monitoring(progress_interval)
            
            # Execute the process
            try:
                result = self.execute_process_step(process_function, **kwargs)
            except HoldException:
                result = self.handle_hold_sequence(process_function, **kwargs)
            except SuspendException:
                result = self.handle_suspend_sequence(process_function, **kwargs)
            
            # Stop progress monitoring
            self.stop_progress_monitoring()
            
            # Set final progress and completion sequence
            if max_duration:
                self.progress = 1.0
                if self.publish_progress:
                    self.publish_progress(self)
            
            # Completion sequence
            self.run_sequence([
                PackMLState.COMPLETING,
                PackMLState.COMPLETE,
                PackMLState.RESETTING,
                PackMLState.IDLE
            ])
            
        except StopException:
            self.stop_progress_monitoring()
            self.run_sequence([
                PackMLState.STOPPING,
                PackMLState.STOPPED,
                PackMLState.RESETTING,
                PackMLState.IDLE
            ], check_exceptions=False)
            
        except AbortException:
            self.stop_progress_monitoring()
            self.run_sequence([
                PackMLState.ABORTING,
                PackMLState.ABORTED,
                PackMLState.CLEARING,
                PackMLState.STOPPED,
                PackMLState.IDLE
            ], check_exceptions=False)
            
        return result
