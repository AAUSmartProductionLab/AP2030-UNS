from MQTT_classes import Proxy, ResponseAsync, Publisher, Subscriber
import time
from PackMLSimulator import PackMLStateMachine
import os

BROKER_ADDRESS = os.getenv("MQTT_BROKER", "hivemq-broker")
BROKER_PORT = int(os.getenv("MQTT_PORT", "1883"))
BASE_TOPIC = "NN/Nybrovej/InnoLab/Unloading"


uuid = ""
simulation_running = False


def VC_response_callback(topic, client, message, properties):
    print(f"Received VC response: {message}")
    global simulation_running
    simulation_running = False

def unload_process():
    global simulation_running
    simulation_running = True

    print("Starting unloading process...")

    VC_cmd_publisher.publish({
        "Command": "StartUnloading",
        "Uuid": uuid
    }, unloadProxy, True)

    while simulation_running:
        time.sleep(0.1)  # Sleep briefly to avoid busy waiting


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
    BASE_TOPIC+"/DATA/Unloading",
    BASE_TOPIC+"/CMD/Unloading",
    "./MQTTSchemas/commandResponse.schema.json",
    "./MQTTSchemas/command.schema.json",
    2,
    unload_callback
)

VC_cmd_publisher = Publisher(
    BASE_TOPIC + "/VC/CMD/Unloading",
    "./MQTTSchemas/command.schema.json",
    2)

VC_cmd_subscriber = Subscriber(
    BASE_TOPIC + "/VC/Response/Unloading",
    "./MQTTSchemas/commandResponse.schema.json",
    2,
    VC_response_callback
)

unloadProxy = Proxy(
    BROKER_ADDRESS,
    BROKER_PORT,
    "UnloadProxy",
    [unload, VC_cmd_publisher, VC_cmd_subscriber]
)

state_machine = PackMLStateMachine(
    BASE_TOPIC, unloadProxy, None, config_path="optimaUnloading.yaml")

# Register asset after MQTT connection is established
unloadProxy.on_ready(state_machine.register_asset)


def main():
    unloadProxy.loop_forever()


if __name__ == "__main__":
    main()
