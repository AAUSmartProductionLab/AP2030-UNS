"""Simulated Syntegon stoppering station — MQTT only.

Its native interface is the MQTT surface that aas-model's
``syntegon_stoppering`` AID describes (base
``NN/Nybrovej/InnoLab/Stoppering``). Every action but Halt is an MQTT 5
request/reply: the terminal reply echoes the request's Correlation Data,
progress acks (State RUNNING) do not. Halt only invokes and is not answered.

================  =======================  ===========================
role              subscribe                publish (response)
================  =======================  ===========================
Stoppering skill  ``CMD/Stoppering``       ``DATA/Stoppering``
Halt skill        ``CMD/Halt``             (none)
Occupy            ``CMD/Occupy``           ``DATA/Occupy``
Release           ``CMD/Release``          ``DATA/Release``
PackML state      ``CMD/State``            ``DATA/State`` (retained)
================  =======================  ===========================

Halt, Occupy, Release and the PackML state are the shared runtime's.
Registration publishes the ``syntegon_stoppering`` Resource with the AID base
set to the broker this station is connected to.
"""

import os
import time
from datetime import datetime, timezone

from packml_runtime.mqtt import Proxy, ResponseAsync
from packml_runtime.simulator import PackMLStateMachine
from services.stations.simple_station import BROKER_ADDRESS, BROKER_PORT, mqtt_resource


BASE_TOPIC = os.getenv("STOPPERING_BASE_TOPIC", "NN/Nybrovej/InnoLab/Stoppering")


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

    stoppering_topic = ResponseAsync(
        f"{BASE_TOPIC}/DATA/Stoppering",
        f"{BASE_TOPIC}/CMD/Stoppering",
        "./MQTTSchemas/commandResponse.schema.json",
        "./MQTTSchemas/command.schema.json",
        2,
        stoppering_callback,
    )
    proxy = Proxy(
        BROKER_ADDRESS,
        BROKER_PORT,
        "StopperingProxy",
        [stoppering_topic],
    )

    state_machine = PackMLStateMachine(BASE_TOPIC, proxy, None, mqtt_resource("syntegonStopperingSystemAAS", BASE_TOPIC))

    proxy.on_ready(state_machine.register_asset)
    proxy.loop_forever()


if __name__ == "__main__":
    main()
