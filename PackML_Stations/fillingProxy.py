from MQTT_classes import Proxy, ResponseAsync, Publisher
import time
import numpy as np
from PackMLSimulator import PackMLStateMachine, PackMLState
import datetime
BROKER_ADDRESS = "192.168.0.104"
BROKER_PORT = 1883
BASE_TOPIC = "NN/Nybrovej/InnoLab/Filling"
target_weight=2

weigh_publisher = Publisher(
        BASE_TOPIC + "/DATA/Weight",
        "./schemas/weight.schema.json", 
        2)


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
    
    # Calculate the maximum PT1 value at end time (for scaling)
    max_pt1_value = 1.0 - np.exp(-duration / time_constant)
    
    # Simulation parameters
    steps= 50
    step_size = duration / steps  # Ensure step size does not exceed duration

    # Store the randomized duration for weight calculation
    if state_machine:
        state_machine.total_duration = duration
        # Generate random target weight with normal distribution
        global target_weight
        target_weight = np.random.normal(2.0, 0.05)
        target_weight = max(1.5, target_weight)  # Ensure minimum weight
        print(f"Target weight: {target_weight}")
    publish_weight(state_machine)

    for i in range(steps):
        time.sleep(step_size)
        if state_machine and state_machine.total_duration:
            current_time = (i+1) * step_size
            # PT1 response formula with scaling to ensure reaching 1.0
            pt1_value = 1.0 - np.exp(-current_time / time_constant)
            state_machine.elapsed_time = current_time
            state_machine.progress = pt1_value / max_pt1_value
            publish_weight(state_machine)


def tare_process(duration=2.0, state_machine=None):
    time.sleep(duration)
    if state_machine and state_machine.total_duration:
        state_machine.elapsed_time = duration
        state_machine.progress = 0.0
        global target_weight#TODO this should ideally be a completly different process and the state machine should be bale to receive multiple
        target_weight = 0.0
        publish_weight(state_machine, reset=True)



def publish_weight(state_machine, reset=False):
    """Publish current progress as weight using PT1 curve"""
    if reset:
        weight = 0.0
    else:
        weight = state_machine.progress * target_weight

    # Generate ISO 8601 timestamp with Z suffix for UTC
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
    
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
    print("mont")
    if state_machine.state == PackMLState.IDLE:
        try:
            duration = 2.0
            state_machine.process_next_command(message, dispense_process, duration)
        except Exception as e:
            print(f"Error in stopper_callback: {e}")


def tare_callback(topic, client, message, properties):
    """Callback handler for dispense commands"""
    if state_machine.state == PackMLState.IDLE:
        try:
            duration = 0.1
            state_machine.process_next_command(message, tare_process, duration)
        except Exception as e:
            print(f"Error in tare_callback: {e}")

def unregister_callback(topic, client, message, properties):
    """Callback handler for unregistering commands by removing them from the queue"""
    try:  
        # Unregister/remove the command from the queue if it's not being processed
        state_machine.unregister_command(message)
        
    except Exception as e:
        print(f"Error in unregister_callback: {e}")


dispense = ResponseAsync(
    BASE_TOPIC+"/DATA/State", 
    BASE_TOPIC+"/CMD/Dispense",
    "./schemas/stationState.schema.json", 
    "./schemas/command.schema.json", 
    2, 
    dispense_callback
)

tare = ResponseAsync(
    BASE_TOPIC+"/DATA/State", 
    BASE_TOPIC+"/CMD/Tare",
    "./schemas/stationState.schema.json", 
    "./schemas/command.schema.json", 
    2, 
    tare_callback
)

register = ResponseAsync(
    BASE_TOPIC+"/DATA/State", 
    BASE_TOPIC+"/CMD/Register",
    "./schemas/stationState.schema.json", 
    "./schemas/command.schema.json", 
    2, 
    register_callback
)
unregister = ResponseAsync(
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
    [dispense,register, unregister,weigh_publisher,tare]
)
state_machine = PackMLStateMachine(dispense, register, unregister, fillProxy, None, publish_weight)


def main():
    """Main entry point for the filling proxy"""

    
    fillProxy.loop_forever()


if __name__ == "__main__":
    main()
