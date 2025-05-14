from MQTT_classes import Proxy, Publisher, ResponseAsync, Subscriber
import time
import numpy as np
from PackMLSimulator import PackMLStateMachine
import datetime
BROKER_ADDRESS = "192.168.0.104"
BROKER_PORT = 1883
BASE_TOPIC = "NN/Nybrovej/InnoLab/Filling"



def dispense_process(mean_duration=2.0, mean_weight=2.0, start_weight=0.0):
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
    steps= 50
    step_size = duration / steps  # Ensure step size does not exceed duration

    # Calculate expected completion percentage at end of simulation
    expected_completion = 1.0 - np.exp(-duration / time_constant)
    
    # Generate random target weight with normal distribution
    # Scale up to compensate for PT1 not reaching 100%
    target_weight = np.random.normal(mean_weight-start_weight, 0.05) / expected_completion
    publish_weight(start_weight)

    for i in range(steps):
        time.sleep(step_size)
        current_time = (i+1) * step_size
        # PT1 response formula with scaling to ensure reaching 1.0
        pt1_value = 1.0 - np.exp(-current_time / time_constant)
        current_weight = start_weight + (pt1_value * target_weight)
        publish_weight(current_weight)

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
        state_machine.start_command(message)
        
    except Exception as e:
        print(f"Error in register_callback: {e}")

def complete_callback(topic, client, message, properties):
    """Callback handler for unregistering commands by removing them from the queue"""
    try:  
        # Unregister/remove the command from the queue if it's not being processed
        state_machine.complete_command(message)
        
    except Exception as e:
        print(f"Error in unregister_callback: {e}")

def abort_callback(topic, client, message, properties):
    """Callback handler for unregistering commands by removing them from the queue"""
    try:  
        # Unregister/remove the command from the queue if it's not being processed
        state_machine.abort_command(message)
        
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

def refill_callback(topic, client, message, properties):
    try:
        duration = 2.0
        weight=2.0
        start_weight_raw = message.get("StartWeight")
        uuid = message.get("Uuid")
        start_weight = float(start_weight_raw)
        if (start_weight > weight):
            raise ValueError("Start weight cannot be greater than target weight")
        state_machine.execute_command(message,refill, dispense_process, duration, weight, start_weight)
    except Exception as e:
        print(f"Error in stopper_callback: {e}")
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
        response = {
            "State": "FAILURE",
            "TimeStamp": timestamp,
            "Uuid": uuid
        }
        refill.publish(response, fillProxy, False)

refill = ResponseAsync(
    BASE_TOPIC+"/DATA/Refill", 
    BASE_TOPIC+"/CMD/Refill",
    "./schemas/commandResponse.schema.json", 
    "./schemas/command.schema.json", 
    2, 
    refill_callback
)


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

start = Subscriber(
    BASE_TOPIC+"/CMD/Start",
    "./schemas/command.schema.json", 
    2, 
    start_callback
)
complete = Subscriber(
    BASE_TOPIC+"/CMD/Complete",
    "./schemas/command.schema.json", 
    2, 
    complete_callback
)
abort = Subscriber(
    BASE_TOPIC+"/CMD/Abort",
    "./schemas/command.schema.json", 
    2, 
    abort_callback
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
    [dispense, start, complete, abort, weigh_publisher, tare, refill]
)
state_machine = PackMLStateMachine(state, fillProxy, None)


def main():
    """Main entry point for the filling proxy"""
    fillProxy.loop_forever()


if __name__ == "__main__":
    main()
