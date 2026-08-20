"""Simulated Syntegon stoppering station.

Implements the full AID action set of the stopper AAS — Stoppering, Halt,
Occupy, Release — plus the PackML state publisher, so the DMP (AIMC)
pipeline can be evaluated with simulated data.

Topics (AID base ``NN/Nybrovej/InnoLab/Stoppering``, see
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

import os
import time
from datetime import datetime, timezone

from packml_runtime.mqtt import Proxy, ResponseAsync
from packml_runtime.simulator import PackMLState, PackMLStateMachine


BROKER_ADDRESS = os.getenv("MQTT_BROKER", "hivemq-broker")
BROKER_PORT = int(os.getenv("MQTT_PORT", "1883"))
BASE_TOPIC = os.getenv("STOPPERING_BASE_TOPIC", "NN/Nybrovej/InnoLab/Stoppering")
CONFIG_PATH = os.getenv("STOPPERING_AAS_CONFIG", "syntegonStoppering.json")


def stopper_process(duration=2.0):
    """Simulate the stoppering process (inserting the stopper)."""
    time.sleep(duration)


def _timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def main():
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
                if state_machine.state == PackMLState.EXECUTE:
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

    proxy = Proxy(
        BROKER_ADDRESS,
        BROKER_PORT,
        "StopperingProxy",
        [stoppering_topic, halt_topic],
    )

    state_machine = PackMLStateMachine(
        BASE_TOPIC,
        proxy,
        None,
        config_path=CONFIG_PATH,
    )

    proxy.on_ready(state_machine.register_asset)
    proxy.loop_forever()


if __name__ == "__main__":
    main()
