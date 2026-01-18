from MQTT_classes import Proxy, Publisher, ResponseAsync
import time
import numpy as np
from PackMLSimulator import PackMLStateMachine
import datetime
import os

BROKER_ADDRESS = os.getenv("MQTT_BROKER", "hivemq-broker")
BROKER_PORT = int(os.getenv("MQTT_PORT", "1883"))
BASE_TOPIC = "NN/Nybrovej/InnoLab/Dispensing"

uuid = ""


def dispense_process(mean_duration=2.0, mean_weight=2.0, start_weight=0.0):
    """
    Simulate dispensing process with PT1 element (first-order lag) characteristics
    Uses normal distribution for both duration and final weight
    """
    # Generate random duration with normal distribution
    duration = np.random.normal(mean_duration, 0.3)
    duration = max(0.5, duration)  # Ensure minimum duration

    # Time constant for PT1 element (affects curve shape)
    time_constant = duration / 3

    # Simulation parameters
    steps = 50
    step_size = duration / steps  # Ensure step size does not exceed duration

    # Calculate expected completion percentage at end of simulation
    expected_completion = 1.0 - np.exp(-duration / time_constant)

    # Generate random target weight with normal distribution
    # Scale up to compensate for PT1 not reaching 100%
    # Ensure the actual dispensed amount is not negative
    target_weight = abs(np.random.normal(
        mean_weight - start_weight, 0.05)) / expected_completion
    publish_weight(start_weight)

    for i in range(steps):
        time.sleep(step_size)
        current_time = (i+1) * step_size
        # PT1 response formula with scaling to ensure reaching 1.0
        pt1_value = 1.0 - np.exp(-current_time / time_constant)
        current_weight = start_weight + (pt1_value * target_weight)
        publish_weight(current_weight)


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
    try:
        duration = 2.0
        weight = 2.0
        global uuid
        uuid = message.get("Uuid")
        state_machine.execute_command(
            message, dispense, dispense_process, duration, weight)
    except Exception as e:
        print(f"Error in dispense_callback: {e}")


def tare_callback(topic, client, message, properties):
    """Callback handler for dispense commands"""
    try:
        duration = 0.1
        state_machine.execute_command(message, tare, tare_process, duration)
    except Exception as e:
        print(f"Error in tare_callback: {e}")


def refill_callback(topic, client, message, properties):
    try:
        duration = 2.0
        weight = 2.0
        start_weight_raw = message.get("StartWeight")
        print(f"Start weight raw: {start_weight_raw}")
        global uuid
        uuid = message.get("Uuid")
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


fillProxy = Proxy(
    BROKER_ADDRESS,
    BROKER_PORT,
    "DispensingProxy",
    [dispense, weigh_publisher, tare, refill]
)
state_machine = PackMLStateMachine(
    BASE_TOPIC, fillProxy, None, config_path="imaDispensing.yaml")

# Register asset after MQTT connection is established
fillProxy.on_ready(state_machine.register_asset)


def main():
    """Main entry point for the dispensing proxy"""
    fillProxy.loop_forever()


if __name__ == "__main__":
    main()
