from MQTT_classes import Proxy, ResponseAsync
import time
from PackMLSimulator import PackMLStateMachine


BROKER_ADDRESS = "192.168.0.104"
BROKER_PORT = 1883
BASE_TOPIC = "NN/Nybrovej/InnoLab/Stoppering"
# Create a global state machine instance




def stopper_process(duration=2.0, state_machine=None):
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


def register_callback(topic, client, message, properties):
    """Callback handler for registering commands without executing them"""
    try:  
        # Register the command without executing
        state_machine.register_command(message)
        
    except Exception as e:
        print(f"Error in register_callback: {e}")

def unregister_callback(topic, client, message, properties):
    """Callback handler for unregistering commands by removing them from the queue"""
    try:  
        # Unregister/remove the command from the queue if it's not being processed
        state_machine.unregister_command(message)
        
    except Exception as e:
        print(f"Error in unregister_callback: {e}")

def stopper_callback(topic, client, message, properties):
    """Callback handler for stopper commands that actually execute"""
    try:
        duration = 2.0
        state_machine.process_next_command(message, stopper_process, duration)
    except Exception as e:
        print(f"Error in stopper_callback: {e}")

"""Main entry point for the stoppering proxy"""
response_async_execute = ResponseAsync(
    BASE_TOPIC+"/DATA/State", 
    BASE_TOPIC+"/CMD/Stopper",
    "./schemas/stationState.schema.json", 
    "./schemas/command.schema.json", 
    2, 
    stopper_callback
)

response_async_register = ResponseAsync(
    BASE_TOPIC+"/DATA/State", 
    BASE_TOPIC+"/CMD/Register",
    "./schemas/stationState.schema.json", 
    "./schemas/command.schema.json", 
    2, 
    register_callback
)

response_async_unregister = ResponseAsync(
    BASE_TOPIC+"/DATA/State", 
    BASE_TOPIC+"/CMD/Unregister",
    "./schemas/stationState.schema.json", 
    "./schemas/command.schema.json", 
    2, 
    unregister_callback
)

stopperProxy = Proxy(
    BROKER_ADDRESS, 
    BROKER_PORT,
    "StopperingProxy", 
    [response_async_execute, response_async_register,response_async_unregister]
)
state_machine = PackMLStateMachine(response_async_execute, response_async_register,response_async_unregister, stopperProxy, None)
state_machine.failureChance=0

def main():
    stopperProxy.loop_forever()

if __name__ == "__main__":
    main()
