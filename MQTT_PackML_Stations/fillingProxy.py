from MQTT_classes import Proxy, ResponseAsync, Publisher
import time
from PackMLSimulator import PackMLStateMachine
BROKER_ADDRESS = "192.168.0.104"
BROKER_PORT = 1883
BASE_TOPIC = "NN/Nybrovej/InnoLab/Filling"


weigh_publisher = Publisher(
        BASE_TOPIC + "/DATA/Weight",
        "./schemas/weight.schema.json", 
        0)


def dispense_process(duration=2.0, state_machine=None):
    """Simulate dispensing process with small increments for continuous progress updates"""
    step_size = 0.1  # Update every 100ms
    steps = int(duration / step_size)
    
    for i in range(steps):
        time.sleep(step_size)
        if state_machine and state_machine.total_duration:
            state_machine.elapsed_time = (i+1) * step_size

    remaining = duration - (steps * step_size)
    if remaining > 0:
        time.sleep(remaining)
        if state_machine and state_machine.total_duration:
            state_machine.elapsed_time = duration
    
    return {"dispensed": True}


def publish_weight(state_machine, reset=False):
    """Publish current progress as weight"""
    progress = state_machine.progress
    max_weight = 2.0    
    if abs(progress - 1.0) < 0.0001:
        weight = max_weight
    else:
        weight = progress * max_weight
    if reset:
        weight = 0.0
    response = {"Weight": weight}
    weigh_publisher.publish(response, state_machine.client)

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
    "./schemas/state.schema.json", 
    "./schemas/command.schema.json", 
    0, 
    dispense_callback
)
response_async_register = ResponseAsync(
BASE_TOPIC+"/DATA/State", 
BASE_TOPIC+"/CMD/Register",
"./schemas/state.schema.json", 
"./schemas/command.schema.json", 
0, 
register_callback
)


fillProxy = Proxy(
    BROKER_ADDRESS, 
    BROKER_PORT,
    "FillingProxy", 
    [response_async_execute,response_async_register, weigh_publisher]
)
state_machine = PackMLStateMachine(response_async_execute,response_async_register, fillProxy, None)


def main():
    """Main entry point for the filling proxy"""

    
    fillProxy.loop_forever()


if __name__ == "__main__":
    main()
