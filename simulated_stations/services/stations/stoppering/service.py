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

Registration publishes the ``syntegon_stoppering`` Resource with the AID base
set to the broker this station is connected to.
"""

import os
import time
from datetime import datetime, timezone

from aas_model.resource_instances import syntegon_stoppering
from aas_model.resource_template.asset_interfaces_description import MQTT_INTERFACE
from packml_runtime.mqtt import Proxy, ResponseAsync, Subscriber
from packml_runtime.simulator import PackMLStateMachine


BROKER_ADDRESS = os.getenv("MQTT_BROKER", "hivemq-broker")
BROKER_PORT = int(os.getenv("MQTT_PORT", "1883"))
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

    def halt_callback(topic, client, message, properties):
        """AID 'Halt' action: stop the machine. Halt only invokes; it is not answered."""
        try:
            if state_machine.is_processing:
                # interrupt the active process and go ABORTING -> ABORTED; an idle halt is a no-op
                state_machine.abort_command()
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
    halt_topic = Subscriber(
        f"{BASE_TOPIC}/CMD/Halt",
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

    resource = syntegon_stoppering()
    resource.asset_interfaces_description.InterfaceTemplateForMQTT[
        MQTT_INTERFACE].EndpointMetadata.base.value = f"mqtt://{BROKER_ADDRESS}:{BROKER_PORT}/{BASE_TOPIC}/"

    state_machine = PackMLStateMachine(BASE_TOPIC, proxy, None, resource=resource)

    proxy.on_ready(state_machine.register_asset)
    proxy.loop_forever()


if __name__ == "__main__":
    main()
