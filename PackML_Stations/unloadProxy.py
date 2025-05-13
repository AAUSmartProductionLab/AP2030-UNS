from MQTT_classes import Proxy, ResponseAsync, Publisher, Subscriber
import time
from PackMLSimulator import PackMLStateMachine

BROKER_ADDRESS = "192.168.0.104"
BROKER_PORT = 1883
BASE_TOPIC = "NN/Nybrovej/InnoLab/Unload"

def unload_process(duration=2.0):
    time.sleep(duration)

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

def unload_callback(topic, client, message, properties):
    """Callback handler for stopper commands"""
    try:
        state_machine.execute_command(message, unload, unload_process)
    except Exception as e:
        print(f"Error in dispense_callback: {e}")


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

state = Publisher(
    BASE_TOPIC+"/DATA/State", 
    "./schemas/stationState.schema.json",
    2
)

unload = ResponseAsync(
    BASE_TOPIC+"/DATA/Unload", 
    BASE_TOPIC+"/CMD/Unload",
    "./schemas/commandResponse.schema.json", 
    "./schemas/command.schema.json", 
    2, 
    unload_callback
)


unloadProxy = Proxy(
    BROKER_ADDRESS, 
    BROKER_PORT,
    "UnloadProxy", 
    [unload, start, complete]
)

state_machine = PackMLStateMachine(state, start, complete, unloadProxy, None)

def main():
    unloadProxy.loop_forever()

if __name__ == "__main__":
    main()
