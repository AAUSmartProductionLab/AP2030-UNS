import os

from packml_runtime.mqtt import Proxy, ResponseAsync
from packml_runtime.simulator import PackMLStateMachine


BROKER_ADDRESS = os.getenv("MQTT_BROKER", "hivemq-broker")
BROKER_PORT = int(os.getenv("MQTT_PORT", "1883"))


def run_simple_station(
    *,
    base_topic: str,
    station_name: str,
    command_label: str,
    config_path: str,
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
        config_path=config_path,
    )

    proxy.on_ready(state_machine.register_asset)
    proxy.loop_forever()
