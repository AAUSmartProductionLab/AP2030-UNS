from MQTT_classes import Proxy, ResponseAsync, Publisher
import time
import numpy as np
from PackMLSimulator import PackMLStateMachine
import datetime
BROKER_ADDRESS = "192.168.0.104"
BROKER_PORT = 1883
BASE_TOPIC = "NN/Nybrovej/InnoLab/Filling"


weigh_publisher = Publisher(
        BASE_TOPIC + "/DATA/Weight",
        "./schemas/weight.schema.json", 
        0)


def dispense_process(mean_duration=2.0, state_machine=None):
    """
    Simulate dispensing process with PT1 element (first-order lag) characteristics
    Uses normal distribution for both duration and final weight
    """
    # Generate random duration with normal distribution
    duration = np.random.normal(mean_duration, 0.3)
    duration = max(0.5, duration)  # Ensure minimum duration
    
    # Time constant for PT1 element (affects curve shape)
    time_constant = duration / 3
    
    # Simulation parameters
    step_size = 0.1  # Update every 100ms
    steps = int(duration / step_size)
    
    # Store the randomized duration for weight calculation
    if state_machine:
        state_machine.total_duration = duration
        # Generate random target weight with normal distribution
        state_machine.target_weight = np.random.normal(2.0, 0.1)
        state_machine.target_weight = max(1.5, state_machine.target_weight)  # Ensure minimum weight
    
    for i in range(steps):
        time.sleep(step_size)
        if state_machine and state_machine.total_duration:
            current_time = (i+1) * step_size
            # PT1 response formula: y(t) = A * (1 - e^(-t/T))
            # Where A is target value (1.0), T is time constant, t is current time
            pt1_progress = 1.0 - np.exp(-current_time / time_constant)
            state_machine.elapsed_time = current_time
            state_machine.pt1_progress = pt1_progress

    remaining = duration - (steps * step_size)
    if remaining > 0:
        time.sleep(remaining)
        if state_machine and state_machine.total_duration:
            state_machine.elapsed_time = duration
            state_machine.pt1_progress = 1.0
    
    return {"dispensed": True}


def publish_weight(state_machine, reset=False):
    """Publish current progress as weight using PT1 curve"""
    if reset:
        weight = 0.0
    elif hasattr(state_machine, 'pt1_progress'):
        # Use PT1 progress for weight calculation
        weight = state_machine.pt1_progress * state_machine.target_weight
    else:
        # Fallback to linear progress if PT1 progress not available
        progress = state_machine.progress
        weight = progress * 2.0
    
    # Generate ISO 8601 timestamp with Z suffix for UTC
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    
    response = {
        "Weight": weight,
        "TimeStamp": timestamp
    }
    weigh_publisher.publish(response, state_machine.client, True)

def register_callback(topic, client, message, properties):
    """Callback handler for registering commands without executing them"""
    try:  
        # Register the command without executing
        state_machine.register_command(message)
        
    except Exception as e:
        print(f"Error in register_callback: {e}")

def dispense_callback(topic, client, message, properties):
    """Callback handler for dispense commands"""
    try:
        duration = 2.0
        state_machine.process_next_command(message, dispense_process, duration,publish_weight)
    except Exception as e:
        print(f"Error in stopper_callback: {e}")

response_async_execute = ResponseAsync(
    BASE_TOPIC+"/DATA/State", 
    BASE_TOPIC+"/CMD/Dispense",
    "./schemas/stationState.schema.json", 
    "./schemas/command.schema.json", 
    2, 
    dispense_callback
)
response_async_register = ResponseAsync(
    BASE_TOPIC+"/DATA/State", 
    BASE_TOPIC+"/CMD/Register",
    "./schemas/stationState.schema.json", 
    "./schemas/command.schema.json", 
    2, 
    register_callback
)
def unregister_callback(topic, client, message, properties):
    """Callback handler for unregistering commands by removing them from the queue"""
    try:  
        # Unregister/remove the command from the queue if it's not being processed
        state_machine.unregister_command(message)
        
    except Exception as e:
        print(f"Error in unregister_callback: {e}")

response_async_unregister = ResponseAsync(
    BASE_TOPIC+"/DATA/State", 
    BASE_TOPIC+"/CMD/Unregister",
    "./schemas/stationState.schema.json", 
    "./schemas/command.schema.json", 
    2, 
    unregister_callback
)
fillProxy = Proxy(
    BROKER_ADDRESS, 
    BROKER_PORT,
    "FillingProxy", 
    [response_async_execute,response_async_register, response_async_unregister,weigh_publisher]
)
state_machine = PackMLStateMachine(response_async_execute,response_async_register,response_async_unregister, fillProxy, None)


def main():
    """Main entry point for the filling proxy"""

    
    fillProxy.loop_forever()


if __name__ == "__main__":
    main()
