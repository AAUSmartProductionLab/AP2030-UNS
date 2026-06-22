from MQTT_classes import Proxy, Publisher, ResponseAsync, Subscriber
import time
import numpy as np
from PackMLSimulator import PackMLStateMachine
import datetime
import os
import paho.mqtt.client as mqtt

## MQTT configuration from environment, with local/docker-compose defaults.
BROKER_ADDRESS = os.getenv("MQTT_BROKER", "localhost")
BROKER_PORT = int(os.getenv("MQTT_PORT", "1883"))
BASE_TOPIC = "NN/Nybrovej/InnoLab/Dispensing"

uuid = ""

simulation_running = False

def VC_message_handling(client, userdata, msg):
    # Tell the process node to spawn the component
    print("{}: {}".format(msg.topic, msg.payload.decode()))

def VC_response_callback(topic, client, message, properties):
    print(f"Received VC response: {message}")
    global simulation_running
    simulation_running = False


# This is the relevant script that should run the dispensing process in Visual Components.
def dispense_process(mean_duration=2.0, mean_weight=2.0, start_weight=0.0):
    """
    Simulate dispensing process with PT1 element (first-order lag) characteristics
    Uses normal distribution for both duration and final weight
    """

    global simulation_running
    simulation_running = True

    VC_cmd_publisher.publish({
        "Command": "StartDispensing",
        "Uuid": uuid
    }, fillProxy, True)

    while simulation_running:
        time.sleep(0.1)  # Sleep briefly to avoid busy waiting


def tare_process(duration=2.0):
    time.sleep(duration)
    publish_weight(0.0, reset=True)


def publish_weight(weight, reset=False):
    """Publish current progress as weight using PT1 curve"""
    if reset:
        weight = 0.0

    # Generate ISO 8601 timestamp with Z suffix for UTC
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec='milliseconds').replace('+00:00', 'Z')
    global uuid
    response = {
        "Weight": weight,
        "TimeStamp": timestamp,
        "Uuid": uuid
    }
    weigh_publisher.publish(response, fillProxy, True)


def dispense_callback(topic, client, message, properties):
    """Callback handler for dispense commands"""
    global uuid
    try:
        # Extract Uuid first, before any operations that might fail
        uuid = message.get("Uuid")
        duration = 2.0
        weight = 2.0
        state_machine.execute_command(
            message, dispense, dispense_process, duration, weight)
    except Exception as e:
        print(f"Error in dispense_callback: {e}")


def tare_callback(topic, client, message, properties):
    """Callback handler for dispense commands"""
    global uuid
    try:
        # Extract Uuid first, before any operations that might fail
        uuid = message.get("Uuid")
        duration = 0.1
        state_machine.execute_command(message, tare, tare_process, duration)
    except Exception as e:
        print(f"Error in tare_callback: {e}")


def refill_callback(topic, client, message, properties):
    global uuid
    try:
        # Extract Uuid first, before any operations that might fail
        uuid = message.get("Uuid")
        duration = 2.0
        weight = 2.0
        start_weight_raw = message.get("StartWeight")
        print(f"Start weight raw: {start_weight_raw}")
        start_weight = float(start_weight_raw)
        if (start_weight > weight):
            raise ValueError(
                "Start weight cannot be greater than target weight")
        state_machine.execute_command(
            message, refill, dispense_process, duration, weight, start_weight)
    except Exception as e:
        print(f"Error in stopper_callback: {e}")
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat(
            timespec='milliseconds').replace('+00:00', 'Z')
        response = {
            "State": "FAILURE",
            "TimeStamp": timestamp,
            "Uuid": uuid
        }
        refill.publish(response, fillProxy, False)


refill = ResponseAsync(
    BASE_TOPIC+"/DATA/Refill",
    BASE_TOPIC+"/CMD/Refill",
    "./MQTTSchemas/commandResponse.schema.json",
    "./MQTTSchemas/command.schema.json",
    2,
    refill_callback
)


dispense = ResponseAsync(
    BASE_TOPIC+"/DATA/Dispensing",
    BASE_TOPIC+"/CMD/Dispensing",
    "./MQTTSchemas/commandResponse.schema.json",
    "./MQTTSchemas/command.schema.json",
    2,
    dispense_callback
)

tare = ResponseAsync(
    BASE_TOPIC+"/DATA/Tare",
    BASE_TOPIC+"/CMD/Tare",
    "./MQTTSchemas/commandResponse.schema.json",
    "./MQTTSchemas/command.schema.json",
    2,
    tare_callback
)


weigh_publisher = Publisher(
    BASE_TOPIC + "/DATA/Weight",
    "./MQTTSchemas/weight.schema.json",
    2)

VC_cmd_publisher = Publisher(
    BASE_TOPIC + "/VC/CMD/Dispensing",
    "./MQTTSchemas/command.schema.json",
    2)

VC_cmd_subscriber = Subscriber(
    BASE_TOPIC + "/VC/Response/Dispensing",
    "./MQTTSchemas/commandResponse.schema.json",
    2,
    VC_response_callback
)


fillProxy = Proxy(
    BROKER_ADDRESS,
    BROKER_PORT,
    "DispensingProxy",
    [dispense, weigh_publisher, VC_cmd_publisher, VC_cmd_subscriber, tare, refill]
)

VC_cmd_subscriber.subscribe(fillProxy)

state_machine = PackMLStateMachine(
    BASE_TOPIC, fillProxy, None, config_path="imaDispensing.yaml") # Possibly change path to ./AASDescriptions/imaDispensing.yaml if needed

# Register asset after MQTT connection is established
fillProxy.on_ready(state_machine.register_asset)


def main():
    """Main entry point for the dispensing proxy"""
    fillProxy.loop_forever()


if __name__ == "__main__":
    main()