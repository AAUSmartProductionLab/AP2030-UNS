from MQTT_classes import Proxy, ResponseAsync, Publisher, Subscriber
import time
from PackMLSimulator import PackMLStateMachine
import os

BROKER_ADDRESS = os.getenv("MQTT_BROKER", "hivemq-broker")
BROKER_PORT = int(os.getenv("MQTT_PORT", "1883"))
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
    "./MQTTSchemas/stationState.schema.json",
    2
)

stopper = ResponseAsync(
    BASE_TOPIC+"/DATA/Stoppering",
    BASE_TOPIC+"/CMD/Stoppering",
    "./MQTTSchemas/commandResponse.schema.json",
    "./MQTTSchemas/command.schema.json",
    2,
    stopper_callback
)


stopperProxy = Proxy(
    BROKER_ADDRESS,
    BROKER_PORT,
    "StopperingProxy",
    [stopper]
)

state_machine = PackMLStateMachine(
    BASE_TOPIC, stopperProxy, None, config_path="syntegonStoppering.yaml")

# Register asset after MQTT connection is established
stopperProxy.on_ready(state_machine.register_asset)


def main():
    stopperProxy.loop_forever()


if __name__ == "__main__":
    main()
