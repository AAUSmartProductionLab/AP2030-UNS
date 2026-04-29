"""Simulated planar shuttle station.

A single shuttle exposes:
  * MoveToPosition action (request on /CMD/XYMotion, response on /DATA/XYMotion)
  * Halt / Occupy / Release (provided by simple_station / PackMLStateMachine)

The shuttle keeps its current (x, y, yaw) pose and publishes it on
``/DATA/Location`` after each move so the AAS Variable ``Location`` resolves
to the actual position. The BT's ``ResourceAt`` predicate compares this pose
against a destination's ``Parameters.Location.Position`` via Euclidean
distance, so no symbolic label mapping is needed here.

Configuration env vars:
  PLANAR_SHUTTLE_BASE_TOPIC   default ``NN/Nybrovej/InnoLab/Planar/Xbot1``
  PLANAR_SHUTTLE_NAME         default ``planarShuttle1``
  PLANAR_SHUTTLE_AAS_CONFIG   default ``planarShuttle1.yaml``
  PLANAR_SHUTTLE_INITIAL_X    default ``0.0``
  PLANAR_SHUTTLE_INITIAL_Y    default ``0.0``
  PLANAR_SHUTTLE_INITIAL_YAW  default ``0.0``
  PLANAR_SHUTTLE_MOVE_DURATION default ``2.0`` (seconds)
"""

import datetime
import os
import time

from packml_runtime.mqtt import Proxy, Publisher, ResponseAsync
from packml_runtime.simulator import PackMLStateMachine


BROKER_ADDRESS = os.getenv("MQTT_BROKER", "hivemq-broker")
BROKER_PORT = int(os.getenv("MQTT_PORT", "1883"))

def _now_iso():
    return (
        datetime.datetime.now(datetime.timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def main():
    base_topic = os.getenv("PLANAR_SHUTTLE_BASE_TOPIC", "NN/Nybrovej/InnoLab/Planar/Xbot1")
    station_name = os.getenv("PLANAR_SHUTTLE_NAME", "planarShuttle1")
    config_path = os.getenv("PLANAR_SHUTTLE_AAS_CONFIG", "planarShuttle1.yaml")
    move_duration = float(os.getenv("PLANAR_SHUTTLE_MOVE_DURATION", "2.0"))

    state = {
        "x": float(os.getenv("PLANAR_SHUTTLE_INITIAL_X", "0.0")),
        "y": float(os.getenv("PLANAR_SHUTTLE_INITIAL_Y", "0.0")),
        "yaw": float(os.getenv("PLANAR_SHUTTLE_INITIAL_YAW", "0.0")),
        "uuid": "",
    }

    location_publisher = Publisher(
        base_topic + "/DATA/Location",
        "./MQTTSchemas/positionStamped.schema.json",
        2,
    )

    def publish_location():
        location_publisher.publish(
            {
                "TimeStamp": _now_iso(),
                "Position": [state["x"], state["y"], state["yaw"]],
            },
            shuttle_proxy,
            retain=True,
        )

    def move_process():
        time.sleep(move_duration)
        publish_location()

    def move_callback(topic, client, message, properties):
        try:
            state["uuid"] = message.get("Uuid", "")
            target = message.get("Position") or message.get("position")
            if target and len(target) >= 2:
                state["x"] = float(target[0])
                state["y"] = float(target[1])
                if len(target) >= 3:
                    state["yaw"] = float(target[2])
            print(f"[{station_name}] MoveToPosition -> ({state['x']}, {state['y']}, {state['yaw']})")
            state_machine.execute_command(message, move_topic, move_process)
        except Exception as exc:
            print(f"[{station_name}] move_callback error: {exc}")

    move_topic = ResponseAsync(
        base_topic + "/DATA/XYMotion",
        base_topic + "/CMD/XYMotion",
        "./MQTTSchemas/commandResponse.schema.json",
        "./MQTTSchemas/moveToPosition.schema.json",
        2,
        move_callback,
    )

    shuttle_proxy = Proxy(
        BROKER_ADDRESS,
        BROKER_PORT,
        f"{station_name}Proxy",
        [move_topic, location_publisher],
    )

    state_machine = PackMLStateMachine(
        base_topic,
        shuttle_proxy,
        None,
        config_path=config_path,
    )

    def _on_ready():
        state_machine.register_asset()
        publish_location()

    shuttle_proxy.on_ready(_on_ready)
    shuttle_proxy.loop_forever()


if __name__ == "__main__":
    main()
