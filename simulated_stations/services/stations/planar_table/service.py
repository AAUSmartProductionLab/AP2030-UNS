"""Simulated planar table parent station.

The planar table only exposes a Halt action and publishes its PackML state
so the orchestration layer can observe whether the table is up. It does not
own any productive skills directly; those live on the child shuttles.
"""

import os

from packml_runtime.mqtt import Proxy
from packml_runtime.simulator import PackMLStateMachine


BROKER_ADDRESS = os.getenv("MQTT_BROKER", "hivemq-broker")
BROKER_PORT = int(os.getenv("MQTT_PORT", "1883"))
BASE_TOPIC = os.getenv("PLANAR_TABLE_BASE_TOPIC", "NN/Nybrovej/InnoLab/Planar")
CONFIG_PATH = os.getenv("PLANAR_TABLE_AAS_CONFIG", "planarTable.yaml")


def main():
    proxy = Proxy(BROKER_ADDRESS, BROKER_PORT, "PlanarTableProxy", [])
    state_machine = PackMLStateMachine(
        BASE_TOPIC,
        proxy,
        None,
        config_path=CONFIG_PATH,
        enable_occupation=False,
        auto_execute=True,
    )
    proxy.on_ready(state_machine.register_asset)
    proxy.loop_forever()


if __name__ == "__main__":
    main()
