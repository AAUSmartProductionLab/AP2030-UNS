from MQTT_classes import Proxy, ResponseAsync, Publisher, Subscriber
import time
from PackMLSimulator import PackMLStateMachine
import os

## Use when build with docker-compose and environment variables for configuration
BROKER_ADDRESS = os.getenv("MQTT_BROKER", "localhost")
BROKER_PORT = int(os.getenv("MQTT_PORT", "1883"))
BASE_TOPIC = "NN/Nybrovej/InnoLab/Stoppering"


uuid = ""
simulation_running = False


def VC_response_callback(topic, client, message, properties):
    print(f"Received VC response: {message}")
    global simulation_running
    simulation_running = False

def stopper_process():
    """
    Simulate dispensing process with PT1 element (first-order lag) characteristics
    Uses normal distribution for both duration and final weight
    """

    global simulation_running
    simulation_running = True

    VC_cmd_publisher.publish({
        "Command": "StartStoppering",
        "Uuid": uuid
    }, stopperProxy, True)

    print("Stoppering process started, waiting for VC response...")
    
    while simulation_running:
        time.sleep(0.1)  # Sleep briefly to avoid busy waiting


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

VC_cmd_publisher = Publisher(
    BASE_TOPIC + "/VC/CMD/Stoppering",
    "./MQTTSchemas/command.schema.json",
    2)

VC_cmd_subscriber = Subscriber(
    BASE_TOPIC + "/VC/Response/Stoppering",
    "./MQTTSchemas/commandResponse.schema.json",
    2,
    VC_response_callback
)

stopperProxy = Proxy(
    BROKER_ADDRESS,
    BROKER_PORT,
    "StopperingProxy",
    [stopper, VC_cmd_publisher, VC_cmd_subscriber]
)

state_machine = PackMLStateMachine(
    BASE_TOPIC, stopperProxy, None, config_path="syntegonStoppering.yaml")

# Register asset after MQTT connection is established
stopperProxy.on_ready(state_machine.register_asset)


def main():
    stopperProxy.loop_forever()


if __name__ == "__main__":
    main()