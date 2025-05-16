from MQTT_classes import Proxy, ResponseAsync, Publisher, Subscriber
import time
from PackMLSimulator import PackMLStateMachine

BROKER_ADDRESS = "192.168.0.104"
BROKER_PORT = 1883
BASE_TOPIC = "NN/Nybrovej/InnoLab/Stoppering"

def stopper_process(duration=2.0):
    time.sleep(duration)

def stopper_callback(topic, client, message, properties):
    """Callback handler for stopper commands"""
    try:
        state_machine.execute_command(message, stopper, stopper_process)
    except Exception as e:
        print(f"Error in dispense_callback: {e}")

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
    [stopper]
)

state_machine = PackMLStateMachine(BASE_TOPIC, stopperProxy, None)

def main():
    stopperProxy.loop_forever()

if __name__ == "__main__":
    main()
