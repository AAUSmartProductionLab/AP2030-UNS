"""Simulated Syntegon stoppering station.

Implements the full AID action set of the stopper AAS — Stoppering, Halt,
Occupy, Release — plus the PackML state publisher, so the DMP (AIMC)
pipeline can be evaluated with simulated data.

The station runs BOTH bindings concurrently against the SAME skill logic:

- **MQTT** (``packml_runtime.mqtt.Proxy``/``ResponseAsync``): the original
  surface, byte-compatible with the existing e2e flows.
- **OPC UA** (``packml_runtime.opcua_server.StationOpcuaServer``): one
  Object + Method per skill (``ns=2;s=<Skill>Method``), the measurement
  streams (``MeasurementFast`` event-updated on PackML transitions,
  ``MeasurementSlow`` slowly varying) and the writable ``Parameter``.

MQTT topics (AID base ``NN/Nybrovej/InnoLab/Stoppering``, see
``AssetInterfacesDescription``):

================  =======================  ===========================
role             subscribe                publish (response)
================  =======================  ===========================
Stoppering skill ``CMD/Stoppering``       ``DATA/Stoppering``
Halt skill       ``CMD/Halt``             ``DATA/Halt``
Occupy           ``CMD/Occupy``           ``DATA/Occupy``
Release          ``CMD/Release``          ``DATA/Release``
PackML state     ``CMD/State``            ``DATA/State`` (retained)
================  =======================  ===========================

Registration uses the full AAS JSON config (``syntegonStoppering.json`` from
``AASDescriptions/Resource/configs/``), which carries both the AID and the
AIMC — the same source of truth the registration service consumes.
"""

import logging
import os
import signal
import threading
import time
from datetime import datetime, timezone

from packml_runtime.mqtt import Proxy, ResponseAsync
from packml_runtime.opcua_server import (
    PARAMETER_DEFAULT, PARAMETER_MAX, PARAMETER_MIN, StationOpcuaServer,
)
from packml_runtime.simulator import PackMLState, PackMLStateMachine


#: Shared effective parameter value — BOTH bindings (the OPC UA write hook
#: and the MQTT parameter command callback) back this one state.
_parameter_state = {"value": PARAMETER_DEFAULT}
_parameter_lock = threading.Lock()


BROKER_ADDRESS = os.getenv("MQTT_BROKER", "hivemq-broker")
BROKER_PORT = int(os.getenv("MQTT_PORT", "1883"))
BASE_TOPIC = os.getenv("STOPPERING_BASE_TOPIC", "NN/Nybrovej/InnoLab/Stoppering")
CONFIG_PATH = os.getenv("STOPPERING_AAS_CONFIG", "syntegonStoppering.json")
OPCUA_ENDPOINT = os.getenv("OPCUA_ENDPOINT", "opc.tcp://0.0.0.0:4840/stoppering/")

#: How long a UA method invocation waits for the skill's terminal reply.
SKILL_REPLY_TIMEOUT_S = 30.0


def stopper_process(duration=2.0):
    """Simulate the stoppering process (inserting the stopper)."""
    time.sleep(duration)


def _timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


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


def build_skill_handler(state_machine, stopper_process=stopper_process):
    """The SAME skill logic the MQTT callbacks run, returning the terminal
    reply for the inline UA OutputArguments of ``StationOpcuaServer``."""
    def opcua_skill_handler(skill, command_uuid):
        if skill == "Stoppering":
            capture = _ReplyCapture()
            state_machine.execute_command(
                {"Uuid": command_uuid}, capture, stopper_process)
            capture.wait(SKILL_REPLY_TIMEOUT_S)
            return capture.terminal or {"State": "FAILURE", "Outcome": 0}
        if skill == "Halt":
            try:
                if state_machine.state == PackMLState.EXECUTE:
                    # interrupt the active process and go ABORTING -> ABORTED
                    state_machine.abort_command()
                # an idle halt is a no-op success; Outcome is the 0-based
                # branch index (non-FOND action -> 0), see commandResponse schema
                return {"State": "SUCCESS", "Outcome": 0}
            except Exception:
                return {"State": "FAILURE", "Outcome": 0}
        if skill == "Occupy":
            if command_uuid in state_machine.uuids or \
                    command_uuid == state_machine.current_processing_uuid:
                return {"State": "FAILURE", "Outcome": 0}
            # accepted/queued; the final SUCCESS/FAILURE for the queued item
            # still flows on the declared MQTT response topic DATA/Occupy
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


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    state_machine = None
    def stoppering_callback(topic, client, message, properties):
        """Productive skill: run the stopper process and report on DATA/Stoppering."""
        try:
            state_machine.execute_command(message, topic, stopper_process)
        except Exception as exc:
            print(f"Error in Stoppering callback: {exc}", flush=True)

    def halt_callback(topic, client, message, properties):
        """AID 'Halt' action: respond on DATA/Halt and stop the machine."""
        try:
            command_uuid = message.get("Uuid")
            if not command_uuid:
                topic.publish({"State": "FAILURE", "TimeStamp": _timestamp(),
                               "Uuid": "UNKNOWN"}, client, False)
                return

            topic.publish({"State": "RUNNING", "TimeStamp": _timestamp(),
                           "Uuid": command_uuid}, client, False)

            try:
                if state_machine.is_processing:
                    # interrupt the active process and go ABORTING -> ABORTED
                    state_machine.abort_command()
                # an idle halt is a no-op success; Outcome is the 0-based
                # branch index (non-FOND action -> 0), see commandResponse schema
                state, outcome = "SUCCESS", 0
            except Exception as exc:
                state, outcome = "FAILURE", 0

            topic.publish({"State": state, "Outcome": outcome,
                           "TimeStamp": _timestamp(), "Uuid": command_uuid},
                          client, False)
        except Exception as exc:
            print(f"Error in Halt callback: {exc}", flush=True)

    def parameter_callback(topic, client, message, properties):
        """AID 'Parameter' write property: validate + store the process
        parameter and acknowledge on DATA/Parameter (the W2 Shape A device
        leg — the DMP awaits this correlated ack). The SAME effective value
        backs the OPC UA Parameter variable (shared module state)."""
        try:
            command_uuid = message.get("Uuid")
            if not command_uuid:
                topic.publish({"State": "FAILURE", "TimeStamp": _timestamp(),
                               "Uuid": "UNKNOWN"}, client, False)
                return

            topic.publish({"State": "RUNNING", "TimeStamp": _timestamp(),
                           "Uuid": command_uuid}, client, False)

            value = message.get("Value")
            try:
                value = float(value)
            except (TypeError, ValueError):
                value = None
            if value is None or not (PARAMETER_MIN <= value <= PARAMETER_MAX):
                topic.publish({"State": "FAILURE", "TimeStamp": _timestamp(),
                               "Uuid": command_uuid}, client, False)
                return

            with _parameter_lock:
                _parameter_state["value"] = value
            topic.publish({"State": "SUCCESS", "Value": value,
                            "TimeStamp": _timestamp(), "Uuid": command_uuid},
                           client, False)
        except Exception as exc:
            print(f"Error in Parameter callback: {exc}", flush=True)

    stoppering_topic = ResponseAsync(
        f"{BASE_TOPIC}/DATA/Stoppering",
        f"{BASE_TOPIC}/CMD/Stoppering",
        "./MQTTSchemas/commandResponse.schema.json",
        "./MQTTSchemas/command.schema.json",
        2,
        stoppering_callback,
    )
    halt_topic = ResponseAsync(
        f"{BASE_TOPIC}/DATA/Halt",
        f"{BASE_TOPIC}/CMD/Halt",
        "./MQTTSchemas/commandResponse.schema.json",
        "./MQTTSchemas/command.schema.json",
        2,
        halt_callback,
    )
    parameter_topic = ResponseAsync(
        f"{BASE_TOPIC}/DATA/Parameter",
        f"{BASE_TOPIC}/CMD/Parameter",
        "./MQTTSchemas/commandResponse.schema.json",
        "./MQTTSchemas/parameterCommand.schema.json",
        2,
        parameter_callback,
    )

    proxy = Proxy(
        BROKER_ADDRESS,
        BROKER_PORT,
        "StopperingProxy",
        [stoppering_topic, halt_topic, parameter_topic],
    )

    state_machine = PackMLStateMachine(
        BASE_TOPIC,
        proxy,
        None,
        config_path=CONFIG_PATH,
    )

    opcua_server = StationOpcuaServer(
        endpoint=OPCUA_ENDPOINT,
        skill_handler=build_skill_handler(state_machine, stopper_process),
        state_provider=lambda: state_machine.state.value,
        transition_counter=lambda: state_machine.transition_count,
        parameter_state=_parameter_state,
        parameter_lock=_parameter_lock,
    )
    opcua_server.start()

    def _dump_task_stacks(signum, frame):
        opcua_server.request_task_stack_dump()

    signal.signal(signal.SIGUSR2, _dump_task_stacks)

    proxy.on_ready(state_machine.register_asset)
    proxy.loop_forever()


if __name__ == "__main__":
    main()
