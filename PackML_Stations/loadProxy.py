from MQTT_classes import Proxy, ResponseAsync, Publisher, Subscriber
import time
from PackMLSimulator import PackMLStateMachine

BROKER_ADDRESS = "172.18.0.1"
BROKER_PORT = 1883
BASE_TOPIC = "NN/Nybrovej/InnoLab/Load"

def load_process(duration=2.0):
    time.sleep(duration)


def load_callback(topic, client, message, properties):
    """Callback handler for stopper commands"""
    try:
        state_machine.execute_command(message, load, load_process)
    except Exception as e:
        print(f"Error in dispense_callback: {e}")



state = Publisher(
    BASE_TOPIC+"/DATA/State", 
    "./schemas/stationState.schema.json",
    2
)

load = ResponseAsync(
    BASE_TOPIC+"/DATA/Load", 
    BASE_TOPIC+"/CMD/Load",
    "./schemas/commandResponse.schema.json", 
    "./schemas/command.schema.json", 
    2, 
    load_callback
)


loadProxy = Proxy(
    BROKER_ADDRESS, 
    BROKER_PORT,
    "LoadingProxy", 
    [load]
)

state_machine = PackMLStateMachine(BASE_TOPIC, loadProxy, None)

def main():
    loadProxy.loop_forever()

if __name__ == "__main__":
    main()
