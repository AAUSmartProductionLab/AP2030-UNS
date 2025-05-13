from MQTT_classes import Proxy, ResponseAsync, Publisher, Subscriber
import time
from PackMLSimulator import PackMLStateMachine

BROKER_ADDRESS = "192.168.0.104"
BROKER_PORT = 1883
BASE_TOPIC = "NN/Nybrovej/InnoLab/Stoppering"

def stopper_process(duration=2.0):
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

def stopper_callback(topic, client, message, properties):
    """Callback handler for stopper commands"""
    try:
        state_machine.execute_command(message, stopper, stopper_process)
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

stopper = ResponseAsync(
    BASE_TOPIC+"/DATA/Stopper", 
    BASE_TOPIC+"/CMD/Stopper",
    "./schemas/commandResponse.schema.json", 
    "./schemas/command.schema.json", 
    2, 
    stopper_callback
)


stopperProxy = Proxy(
    BROKER_ADDRESS, 
    BROKER_PORT,
    "StopperingProxy", 
    [stopper, start,complete]
)

state_machine = PackMLStateMachine(state, start, complete, stopperProxy, None)

def main():
    stopperProxy.loop_forever()

if __name__ == "__main__":
    main()
