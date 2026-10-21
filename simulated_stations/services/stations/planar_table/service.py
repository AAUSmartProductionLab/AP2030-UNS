"""Simulated planar table parent station.

The planar table only exposes a Halt action and publishes its PackML state
so the orchestration layer can observe whether the table is up. It does not
own any productive skills directly; those live on the child shuttles.
"""

import os

from packml_runtime.mqtt import Proxy
from packml_runtime.simulator import PackMLStateMachine
from services.stations.simple_station import BROKER_ADDRESS, BROKER_PORT, mqtt_resource


BASE_TOPIC = os.getenv("PLANAR_TABLE_BASE_TOPIC", "NN/Nybrovej/InnoLab/Planar")


def main():
    proxy = Proxy(BROKER_ADDRESS, BROKER_PORT, "PlanarTableProxy", [])
    state_machine = PackMLStateMachine(
        BASE_TOPIC,
        proxy,
        None,
        mqtt_resource("planarTableAAS", BASE_TOPIC),
        enable_occupation=False,
        auto_execute=True,
    )
    proxy.on_ready(state_machine.register_asset)
    proxy.loop_forever()


if __name__ == "__main__":
    main()
