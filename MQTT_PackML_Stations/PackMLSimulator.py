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

# Module-level queue variables (one per process)
_command_queue = queue.Queue()
_queue_lock = threading.Lock()
_is_processing = False
_command_uuids = []  # Track all queued command UUIDs

def queue_command(command_data):
    """Add a command to the queue and try to process it"""
    # Extract command UUID if available
    message = command_data[2]  # Message is at index 2
    command_uuid = message.get("CommandUuid")
    
    with _queue_lock:
        _command_queue.put(command_data)
        
        # Track command UUID if available
        if command_uuid:
            _command_uuids.append(command_uuid)
    
    # Try to process queue if not already processing
    threading.Thread(target=process_next_command, daemon=True).start()

def process_next_command():
    """Process the next command in queue"""
    global _is_processing
    
    with _queue_lock:
        # Skip if already processing or queue is empty
        if _is_processing or _command_queue.empty():
            return
        _is_processing = True
    
    try:
        # Get next command from queue
        command_data = _command_queue.get()
        
        # Unpack with variable length support
        topic, client, message, properties, process_function, *rest = command_data
        
        # Extract command UUID if available
        command_uuid = message.get("CommandUuid")
        
        # Create new state machine and process the command
        state_machine = PackMLStateMachine(topic, client, properties)
        if command_uuid:
            state_machine.CommandUuid = command_uuid
        
        # Set up progress callback if provided
        if len(rest) > 0:
            state_machine.publish_progress = rest[0]
        
        # Extract parameters
        kwargs = {}
        if "duration" in message:
            kwargs["duration"] = message["duration"]
        if "max_duration" in message:
            kwargs["max_duration"] = message["max_duration"]
        
        # Process the command
        state_machine.run_state_machine(process_function, **kwargs)
                    
    except Exception as e:
        print(f"Error in queue processing: {e}")
    
    finally:
        with _queue_lock:
            _is_processing = False
            # Check if there are more commands
            if not _command_queue.empty():
                threading.Thread(target=process_next_command, daemon=True).start()


class PackMLStateMachine:
    def __init__(self, topic, client, properties, publish_progress=None):
        self.state = PackMLState.IDLE
        self.topic = topic
        self.client = client
        self.properties = properties
        self.CommandUuid = None
        self.publish_progress = publish_progress
        self.failureChance=0.01
        # Progress tracking
        self.total_duration = 0
        self.elapsed_time = 0
        self.progress = 0
        
        # Threading control
        self.progress_thread = None
        self.stop_progress = threading.Event()
    
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
            
            # Remove UUID from tracking list when command completes
            with _queue_lock:
                if prev_uuid and prev_uuid in _command_uuids:
                    _command_uuids.remove(prev_uuid)
                    
                # Get fresh queue state
                queued_uuids = _command_uuids.copy()
                
                # For IDLE state with empty queue, use empty array
                response["ProcessQueue"] = queued_uuids if queued_uuids else []
        else:
            # Regular handling for other states
            with _queue_lock:
                queued_uuids = _command_uuids.copy()
                
                # Include current UUID if applicable
                if self.CommandUuid and self.CommandUuid not in queued_uuids:
                    response["ProcessQueue"] = [self.CommandUuid] + queued_uuids
                else:
                    response["ProcessQueue"] = queued_uuids
        
        self.topic.publish(response, self.client, self.properties)
        
        # Process next command if we're transitioning to IDLE
        if new_state == PackMLState.IDLE:
            threading.Thread(target=process_next_command, daemon=True).start()
        
        time.sleep(delay)
    
    def run_sequence(self, states, delay=0.1):
        """Run a sequence of states with checks between each"""
        for state in states:
            self.transition_to(state, delay)
            self.check_random_exceptions(in_execute=(state == PackMLState.EXECUTE))
    
    def execute_process_step(self, process_function, **kwargs):
        """Execute a single step of the process with timing and progress tracking"""
        process_start = time.time()
        
        try:
            # Check for exceptions before starting
            self.check_random_exceptions(in_execute=True)
            
            # Adjust duration based on remaining time
            if self.total_duration:
                remaining_time = self.total_duration - self.elapsed_time
                kwargs['duration'] = min(kwargs.get('duration', remaining_time), remaining_time)
            
            # Pass state machine reference to process function
            kwargs['state_machine'] = self
            
            # Execute the process
            result = process_function(**kwargs)
            
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
            ])
            
        except AbortException:
            self.stop_progress_monitoring()
            self.run_sequence([
                PackMLState.ABORTING,
                PackMLState.ABORTED,
                PackMLState.CLEARING,
                PackMLState.STOPPED,
                PackMLState.IDLE
            ])
            
        return result
