from MQTT_classes import Proxy, ResponseAsync, Publisher, Subscriber
import time
from PackMLSimulator import PackMLStateMachine
import os

BROKER_ADDRESS = os.getenv("MQTT_BROKER", "hivemq-broker")
BROKER_PORT = int(os.getenv("MQTT_PORT", "1883"))
BASE_TOPIC = "NN/Nybrovej/InnoLab/Unload"


def unload_process(duration=2.0):
    time.sleep(duration)


def unload_callback(topic, client, message, properties):
    """Callback handler for stopper commands"""
    try:
        state_machine.execute_command(message, unload, unload_process)
    except Exception as e:
        print(f"Error in dispense_callback: {e}")


state = Publisher(
    BASE_TOPIC+"/DATA/State",
    "./MQTTSchemas/stationState.schema.json",
    2
)

unload = ResponseAsync(
    BASE_TOPIC+"/DATA/Unload",
    BASE_TOPIC+"/CMD/Unload",
    "./MQTTSchemas/commandResponse.schema.json",
    "./MQTTSchemas/command.schema.json",
    2,
    unload_callback
)


unloadProxy = Proxy(
    BROKER_ADDRESS,
    BROKER_PORT,
    "UnloadProxy",
    [unload]
)

state_machine = PackMLStateMachine(
    BASE_TOPIC, unloadProxy, None, config_path="optimaUnloading.yaml")

# Register asset after MQTT connection is established
unloadProxy.on_ready(state_machine.register_asset)


def main():
    unloadProxy.loop_forever()


if __name__ == "__main__":
    main()
