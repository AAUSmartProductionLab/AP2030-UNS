"""Simulated Syntegon dispensing (filling) station.

Same dual-binding structure as the stoppering station — the CODE runs both
bindings concurrently against the SAME skill logic — but its AAS is
authored/bound OPC UA ONLY (the AID carries InterfaceTemplateForOPCUA and
the AIMC maps OPC UA affordances only), exercising the milo method-call /
node-write DMP legs.

- **MQTT** (``packml_runtime.mqtt``): the original dispensing surface
  (Dispensing/Tare/Refill), byte-compatible with the existing flows.
- **OPC UA** (``packml_runtime.opcua_server.StationOpcuaServer``): one
  Object + Method per skill (``ns=2;s=<Skill>Method`` — Dispensing, Tare,
  Refill), the measurement streams (``MeasurementFast`` on PackML
  transitions, ``MeasurementSlow`` slowly varying) and the writable
  ``Parameter``.

Skills (CCD ControlComponent semantics):
================  =======================  ===========================
role             command                  terminal reply
================  =======================  ===========================
Dispensing skill ``CMD/Dispensing``       ``DATA/Dispensing``
Tare skill       ``CMD/Tare``             ``DATA/Tare``
Refill skill     ``CMD/Refill``           ``DATA/Refill``
Occupy           ``CMD/Occupy``           ``DATA/Occupy``
Release          ``CMD/Release``          ``DATA/Release``
PackML state     ``CMD/State``            ``DATA/State`` (retained)
================  =======================  ===========================

Registration publishes the full AAS JSON config (the OPC-UA-only variant
of ``syntegonDispensing.json`` from ``AASDescriptions/Resource/configs/``).
"""

import json
import logging
import os
import signal
import threading
import time

from packml_runtime.mqtt import Proxy, Publisher, ResponseAsync
from packml_runtime.opcua_server import StationOpcuaServer
from packml_runtime.simulator import PackMLStateMachine, PackMLState
import numpy as np
import datetime

BROKER_ADDRESS = os.getenv("MQTT_BROKER", "hivemq-broker")
BROKER_PORT = int(os.getenv("MQTT_PORT", "1883"))
BASE_TOPIC = "NN/Nybrovej/InnoLab/Dispensing"
AAS_CONFIG = os.getenv("DISPENSING_AAS_CONFIG", "syntegonDispensing.json")
OPCUA_ENDPOINT = os.getenv("OPCUA_ENDPOINT", "opc.tcp://0.0.0.0:4840/dispensing/")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

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


def build_skill_handler(state_machine):
    """The SAME skill logic the MQTT callbacks run, returning the terminal
    reply for the inline UA OutputArguments of ``StationOpcuaServer``."""
    def opcua_skill_handler(skill, command_uuid):
        if skill in ("Dispensing", "Refill"):
            capture = _ReplyCapture()
            state_machine.execute_command(
                {"Uuid": command_uuid}, capture, dispense_process)
            capture.wait(SKILL_REPLY_TIMEOUT_S)
            return capture.terminal or {"State": "FAILURE", "Outcome": 0}
        if skill == "Tare":
            capture = _ReplyCapture()
            state_machine.execute_command(
                {"Uuid": command_uuid}, capture, tare_process, 0.1)
            capture.wait(SKILL_REPLY_TIMEOUT_S)
            return capture.terminal or {"State": "FAILURE", "Outcome": 0}
        if skill == "Halt":
            try:
                if state_machine.is_processing:
                    state_machine.abort_command()
                return {"State": "SUCCESS", "Outcome": 0}
            except Exception:
                return {"State": "FAILURE", "Outcome": 0}
        if skill == "Occupy":
            if command_uuid in state_machine.uuids or \
                    command_uuid == state_machine.current_processing_uuid:
                return {"State": "FAILURE", "Outcome": 0}
            state_machine.register_command(command_uuid)
            return {"State": "SUCCESS", "Outcome": 0}
        if skill == "Release":
            active = state_machine.is_processing and \
                command_uuid == state_machine.current_processing_uuid
            if active or command_uuid in state_machine.uuids:
                state_machine.unregister_command(command_uuid)
                return {"State": "SUCCESS", "Outcome": 0}
            return {"State": "FAILURE", "Outcome": 0}
        return {"State": "FAILURE", "Outcome": 0}
    return opcua_skill_handler


class _ReplyCapture:
    """Stands in for a ``ResponseAsync`` topic: captures every reply the
    state machine publishes for one skill invocation and flags the terminal
    one (``State`` is SUCCESS/FAILURE — RUNNING is intermediate)."""

    def __init__(self):
        self.terminal = None
        self._event = threading.Event()

    def publish(self, message, client=None, *args, **kwargs):
        if isinstance(message, dict) and \
                str(message.get("State", "")).upper() in ("SUCCESS", "FAILURE"):
            self.terminal = message
            self._event.set()

    def wait(self, timeout):
        return self._event.wait(timeout)


fillProxy = Proxy(
    BROKER_ADDRESS,
    BROKER_PORT,
    "DispensingProxy",
    [dispense, weigh_publisher, tare, refill]
)
state_machine = PackMLStateMachine(
    BASE_TOPIC, fillProxy, None, config_path=AAS_CONFIG)

# shared parameter state for both bindings (the same hook the stoppering uses)
PARAMETER_DEFAULT = 50.0
_parameter_state = {"value": PARAMETER_DEFAULT}
_parameter_lock = threading.Lock()
SKILL_REPLY_TIMEOUT_S = 10.0

opcua_server = StationOpcuaServer(
    endpoint=OPCUA_ENDPOINT,
    skills=("Halt", "Occupy", "Release", "Dispensing", "Tare", "Refill"),
    skill_handler=build_skill_handler(state_machine),
    # The AIMC Lua for the OPC UA leg reads the StationState node as a JSON
    # object (PackMLState/OccupationState), mirroring the MQTT DATA/State
    # payload shape (ProcessQueue) the MQTT-bound stations publish.
    state_provider=lambda: json.dumps({
        "PackMLState": state_machine.state.value,
        "OccupationState": list(state_machine.uuids),
    }),
    transition_counter=lambda: state_machine.transition_count,
    parameter_state=_parameter_state,
    parameter_lock=_parameter_lock,
)
opcua_server.start()


def _dump_task_stacks(signum, frame):
    opcua_server.request_task_stack_dump()


signal.signal(signal.SIGUSR2, _dump_task_stacks)

# Register asset after MQTT connection is established
fillProxy.on_ready(state_machine.register_asset)


def main():
    """Main entry point for the dispensing proxy"""
    fillProxy.loop_forever()


if __name__ == "__main__":
    main()
