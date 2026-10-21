import json
import os
from pathlib import Path

from packml_runtime.mqtt import Proxy, ResponseAsync
from packml_runtime.simulator import PackMLStateMachine


BROKER_ADDRESS = os.getenv("MQTT_BROKER", "hivemq-broker")
BROKER_PORT = int(os.getenv("MQTT_PORT", "1883"))

# The Resources aas-model authors for the stations (resources/export.py).
RESOURCES = Path(__file__).resolve().parents[2] / "resources"


def load_resource(id_short: str, interface: str, base: str) -> dict:
    """The exported Resource ``id_short``, its AID base for ``interface``
    (e.g. ``InterfaceTemplateForMQTT``) set to ``base``."""
    resource = json.loads((RESOURCES / f"{id_short}.json").read_text(encoding="utf-8"))
    for description in resource["asset_interfaces_description"][interface].values():
        description["EndpointMetadata"]["base"]["value"] = base
    return resource


def mqtt_resource(id_short: str, base_topic: str) -> dict:
    """The exported Resource ``id_short``, its MQTT base set to the broker
    and topic this station serves (the AID base the DMP connects to)."""
    return load_resource(id_short, "InterfaceTemplateForMQTT",
                         f"mqtt://{BROKER_ADDRESS}:{BROKER_PORT}/{base_topic}/")


def run_simple_station(
    *,
    base_topic: str,
    station_name: str,
    command_label: str,
    resource: str,
    process_function,
):
    """Run a single-command PackML station using shared runtime components."""

    proxy = None
    state_machine = None

    def command_callback(topic, client, message, properties):
        try:
            state_machine.execute_command(message, command_topic, process_function)
        except Exception as exc:
            print(f"Error in {station_name} callback: {exc}")

    command_topic = ResponseAsync(
        f"{base_topic}/DATA/{command_label}",
        f"{base_topic}/CMD/{command_label}",
        "./MQTTSchemas/commandResponse.schema.json",
        "./MQTTSchemas/command.schema.json",
        2,
        command_callback,
    )

    proxy = Proxy(
        BROKER_ADDRESS,
        BROKER_PORT,
        f"{station_name}Proxy",
        [command_topic],
    )

    state_machine = PackMLStateMachine(
        base_topic,
        proxy,
        None,
        mqtt_resource(resource, base_topic),
    )

    proxy.on_ready(state_machine.register_asset)
    proxy.loop_forever()
