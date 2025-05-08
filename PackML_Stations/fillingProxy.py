from MQTT_classes import Proxy, Publisher, ResponseAsync
import time
import numpy as np
from PackMLSimulator import PackMLStateMachine
import datetime
BROKER_ADDRESS = "192.168.0.104"
BROKER_PORT = 1883
BASE_TOPIC = "NN/Nybrovej/InnoLab/Filling"




def dispense_process(mean_duration=2.0, mean_weight=2.0):
    """
    Simulate dispensing process with PT1 element (first-order lag) characteristics
    Uses normal distribution for both duration and final weight
    """
    # Generate random duration with normal distribution
    duration = np.random.normal(mean_duration, 0.3)
    duration = max(0.5, duration)  # Ensure minimum duration
    
    # Time constant for PT1 element (affects curve shape)
    time_constant = duration / 3
    
    # Calculate the maximum PT1 value at end time (for scaling)
    max_pt1_value = 1.0 - np.exp(-duration / time_constant)
    
    # Simulation parameters
    steps= 50
    step_size = duration / steps  # Ensure step size does not exceed duration

    # Generate random target weight with normal distribution
    target_weight = np.random.normal(mean_weight, 0.05)
    target_weight = max(1.5, target_weight)  # Ensure minimum weight
    publish_weight(0.0,reset=True)

    for i in range(steps):
        time.sleep(step_size)
        current_time = (i+1) * step_size
        # PT1 response formula with scaling to ensure reaching 1.0
        pt1_value = 1.0 - np.exp(-current_time / time_constant)
        publish_weight(pt1_value)

def tare_process(duration=2.0, state_machine=None):
    time.sleep(duration)
    publish_weight(0.0,reset=True)

def publish_weight(weight, reset=False):
    """Publish current progress as weight using PT1 curve"""
    if reset:
        weight = 0.0

    # Generate ISO 8601 timestamp with Z suffix for UTC
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
    
    response = {
        "Weight": weight,
        "TimeStamp": timestamp
    }
    weigh_publisher.publish(response, fillProxy, True)

def start_callback(topic, client, message, properties):
    """Callback handler for registering commands without executing them"""
    try:  
        # Register the command without executing
        state_machine.start_command(message, start)
        
    except Exception as e:
        print(f"Error in register_callback: {e}")

def complete_callback(topic, client, message, properties):
    """Callback handler for unregistering commands by removing them from the queue"""
    try:  
        # Unregister/remove the command from the queue if it's not being processed
        state_machine.complete_command(message, complete)
        
    except Exception as e:
        print(f"Error in unregister_callback: {e}")

def dispense_callback(topic, client, message, properties):
    """Callback handler for dispense commands"""
    try:
        duration = 2.0
        weight=2.0
        state_machine.execute_command(message,dispense, dispense_process, duration, weight)
    except Exception as e:
        print(f"Error in dispense_callback: {e}")

def tare_callback(topic, client, message, properties):
    """Callback handler for dispense commands"""
    try:
        duration = 0.1
        state_machine.execute_command(message, tare, tare_process, duration)
    except Exception as e:
        print(f"Error in tare_callback: {e}")



dispense = ResponseAsync(
    BASE_TOPIC+"/DATA/Dispense", 
    BASE_TOPIC+"/CMD/Dispense",
    "./schemas/commandResponse.schema.json", 
    "./schemas/command.schema.json", 
    2, 
    dispense_callback
)

tare = ResponseAsync(
    BASE_TOPIC+"/DATA/Tare", 
    BASE_TOPIC+"/CMD/Tare",
    "./schemas/commandResponse.schema.json", 
    "./schemas/command.schema.json", 
    2, 
    tare_callback
)

start = ResponseAsync(
    BASE_TOPIC+"/DATA/Start", 
    BASE_TOPIC+"/CMD/Start",
    "./schemas/commandResponse.schema.json", 
    "./schemas/command.schema.json", 
    2, 
    start_callback
)
complete = ResponseAsync(
    BASE_TOPIC+"/DATA/Complete", 
    BASE_TOPIC+"/CMD/Complete",
    "./schemas/commandResponse.schema.json", 
    "./schemas/command.schema.json", 
    2, 
    complete_callback
)

state = Publisher(
    BASE_TOPIC+"/DATA/State", 
    "./schemas/stationState.schema.json",
    2
)

weigh_publisher = Publisher(
        BASE_TOPIC + "/DATA/Weight",
        "./schemas/weight.schema.json", 
        2)


fillProxy = Proxy(
    BROKER_ADDRESS, 
    BROKER_PORT,
    "FillingProxy", 
    [dispense, start, complete, weigh_publisher, tare]
)
state_machine = PackMLStateMachine(state, fillProxy, None)


def main():
    """Main entry point for the filling proxy"""
    fillProxy.loop_forever()


if __name__ == "__main__":
    main()
