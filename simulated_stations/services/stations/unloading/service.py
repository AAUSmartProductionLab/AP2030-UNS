import os
import time

from packml_runtime.mqtt import Proxy, ResponseAsync
from packml_runtime.simulator import PackMLStateMachine


BASE_TOPIC = "NN/Nybrovej/InnoLab/Unloading"
BROKER_ADDRESS = os.getenv("MQTT_BROKER", "hivemq-broker")
BROKER_PORT = int(os.getenv("MQTT_PORT", "1883"))
UNLOAD_DURATION = float(os.getenv("UNLOAD_DURATION", "2.0"))
SCRAP_DURATION = float(os.getenv("SCRAP_DURATION", "1.5"))


def unload_process(duration=UNLOAD_DURATION):
    time.sleep(duration)


def scrap_process(duration=SCRAP_DURATION):
    time.sleep(duration)


def main():
    proxy = None
    state_machine = None

    def make_callback(topic_obj, process_fn, label):
        def _cb(topic, client, message, properties):
            try:
                state_machine.execute_command(message, topic_obj, process_fn)
            except Exception as exc:
                print(f"Error in Unload {label} callback: {exc}")
        return _cb

    unloading_topic = ResponseAsync(
        f"{BASE_TOPIC}/DATA/Unloading",
        f"{BASE_TOPIC}/CMD/Unloading",
        "./MQTTSchemas/commandResponse.schema.json",
        "./MQTTSchemas/command.schema.json",
        2,
        None,
    )
    unloading_topic.callback_method = make_callback(unloading_topic, unload_process, "Unloading")

    scrap_topic = ResponseAsync(
        f"{BASE_TOPIC}/DATA/Scrap",
        f"{BASE_TOPIC}/CMD/Scrap",
        "./MQTTSchemas/commandResponse.schema.json",
        "./MQTTSchemas/command.schema.json",
        2,
        None,
    )
    scrap_topic.callback_method = make_callback(scrap_topic, scrap_process, "Scrap")

    proxy = Proxy(
        BROKER_ADDRESS,
        BROKER_PORT,
        "UnloadProxy",
        [unloading_topic, scrap_topic],
    )

    state_machine = PackMLStateMachine(
        BASE_TOPIC,
        proxy,
        None,
        config_path="optimaUnloading.yaml",
    )

    proxy.on_ready(state_machine.register_asset)
    proxy.loop_forever()


if __name__ == "__main__":
    main()
