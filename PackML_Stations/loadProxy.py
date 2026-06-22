from MQTT_classes import Proxy, ResponseAsync, Publisher, Subscriber
import time
from PackMLSimulator import PackMLStateMachine

import os

BROKER_ADDRESS = os.getenv("MQTT_BROKER", "localhost")
BROKER_PORT = int(os.getenv("MQTT_PORT", "1883"))
BASE_TOPIC = "NN/Nybrovej/InnoLab/Loading"

uuid = ""
simulation_running = False


def VC_response_callback(topic, client, message, properties):
    print(f"Received VC response: {message}")
    global simulation_running
    simulation_running = False

def load_process():
    global simulation_running
    simulation_running = True

    print("Starting loading process...")

    VC_cmd_publisher.publish({
        "Command": "StartLoading",
        "Uuid": uuid
    }, loadProxy, True)

    while simulation_running:
        time.sleep(0.1)  # Sleep briefly to avoid busy waiting


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

VC_cmd_publisher = Publisher(
    BASE_TOPIC + "/VC/CMD/Loading",
    "./MQTTSchemas/command.schema.json",
    2)

VC_cmd_subscriber = Subscriber(
    BASE_TOPIC + "/VC/Response/Loading",
    "./MQTTSchemas/commandResponse.schema.json",
    2,
    VC_response_callback
)

loadProxy = Proxy(
    BROKER_ADDRESS,
    BROKER_PORT,
    "LoadingProxy",
    [load, VC_cmd_publisher, VC_cmd_subscriber]
)

state_machine = PackMLStateMachine(
    BASE_TOPIC, loadProxy, None, config_path="imaLoadingSystem.yaml")

# Register asset after MQTT connection is established
loadProxy.on_ready(state_machine.register_asset)


def main():
    loadProxy.loop_forever()


if __name__ == "__main__":
    main()
