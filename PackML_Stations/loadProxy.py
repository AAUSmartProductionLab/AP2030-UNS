from MQTT_classes import Proxy, ResponseAsync, Publisher, Subscriber
import time
from PackMLSimulator import PackMLStateMachine

import os

BROKER_ADDRESS = os.getenv("MQTT_BROKER", "hivemq-broker")
BROKER_PORT = int(os.getenv("MQTT_PORT", "1883"))
BASE_TOPIC = "NN/Nybrovej/InnoLab/Loading"


def load_process(duration=15.0):
    time.sleep(duration)


def load_callback(topic, client, message, properties):
    """Callback handler for load commands"""
    try:
        state_machine.execute_command(message, load, load_process)
    except Exception as e:
        print(f"Error in dispense_callback: {e}")


state = Publisher(
    BASE_TOPIC+"/DATA/State",
    "./MQTTSchemas/stationState.schema.json",
    2
)

load = ResponseAsync(
    BASE_TOPIC+"/DATA/Loading",
    BASE_TOPIC+"/CMD/Loading",
    "./MQTTSchemas/commandResponse.schema.json",
    "./MQTTSchemas/command.schema.json",
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
