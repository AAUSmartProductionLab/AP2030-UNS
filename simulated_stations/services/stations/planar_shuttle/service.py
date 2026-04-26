"""Simulated planar shuttle station.

A single shuttle exposes:
  * MoveToPosition action (request on /CMD/XYMotion, response on /DATA/XYMotion)
  * Halt / Occupy / Release (provided by simple_station / PackMLStateMachine)

The shuttle keeps an internal `location` string and publishes it on
``/DATA/Location`` after each move so the AAS Variable ``Location`` resolves.
The mapping between an (X, Y) target and a symbolic location label is taken
from the env var ``PLANAR_SHUTTLE_LOCATIONS`` (JSON dict of
``label -> [x, y]``); the closest label to the requested position is chosen.

Configuration env vars:
  PLANAR_SHUTTLE_BASE_TOPIC   default ``NN/Nybrovej/InnoLab/Planar/Xbot1``
  PLANAR_SHUTTLE_NAME         default ``planarShuttle1``
  PLANAR_SHUTTLE_AAS_CONFIG   default ``planarShuttle1.yaml``
  PLANAR_SHUTTLE_LOCATIONS    default mapping covering the aseptic line.
  PLANAR_SHUTTLE_INITIAL      default ``imaLoadingStation``
  PLANAR_SHUTTLE_MOVE_DURATION default ``2.0`` (seconds)
"""

import datetime
import json
import math
import os
import time

from packml_runtime.mqtt import Proxy, Publisher, ResponseAsync
from packml_runtime.simulator import PackMLStateMachine


BROKER_ADDRESS = os.getenv("MQTT_BROKER", "hivemq-broker")
BROKER_PORT = int(os.getenv("MQTT_PORT", "1883"))

DEFAULT_LOCATIONS = {
    "imaLoadingStation": [0.0, 0.0],
    "imaDispensingStation": [240.0, 0.0],
    "syntegonStopperingStation": [480.0, 0.0],
    "omronCameraStation": [480.0, 240.0],
    "cytivaCappingStation": [240.0, 240.0],
    "optimaUnloadingStation": [0.0, 240.0],
}


def _now_iso():
    return (
        datetime.datetime.now(datetime.timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _nearest_label(target_xy, locations):
    """Return the location label whose anchor is closest to ``target_xy``."""
    if not target_xy or len(target_xy) < 2:
        return None
    tx, ty = float(target_xy[0]), float(target_xy[1])
    best = None
    best_d2 = float("inf")
    for label, anchor in locations.items():
        ax, ay = float(anchor[0]), float(anchor[1])
        d2 = (ax - tx) ** 2 + (ay - ty) ** 2
        if d2 < best_d2:
            best = label
            best_d2 = d2
    return best


def main():
    base_topic = os.getenv("PLANAR_SHUTTLE_BASE_TOPIC", "NN/Nybrovej/InnoLab/Planar/Xbot1")
    station_name = os.getenv("PLANAR_SHUTTLE_NAME", "planarShuttle1")
    config_path = os.getenv("PLANAR_SHUTTLE_AAS_CONFIG", "planarShuttle1.yaml")
    move_duration = float(os.getenv("PLANAR_SHUTTLE_MOVE_DURATION", "2.0"))
    initial_location = os.getenv("PLANAR_SHUTTLE_INITIAL", "imaLoadingStation")

    locations_raw = os.getenv("PLANAR_SHUTTLE_LOCATIONS")
    if locations_raw:
        try:
            locations = json.loads(locations_raw)
        except json.JSONDecodeError as exc:
            print(f"[{station_name}] PLANAR_SHUTTLE_LOCATIONS invalid JSON: {exc}; using defaults")
            locations = dict(DEFAULT_LOCATIONS)
    else:
        locations = dict(DEFAULT_LOCATIONS)

    state = {
        "location": initial_location,
        "uuid": "",
        "yaw": 0.0,
    }

    location_publisher = Publisher(
        base_topic + "/DATA/Location",
        "./MQTTSchemas/planarLocation.schema.json",
        2,
    )

    def publish_location():
        anchor = locations.get(state["location"], [0.0, 0.0])
        x = float(anchor[0])
        z = float(anchor[1])
        location_publisher.publish(
            {
                "TimeStamp": _now_iso(),
                "Position": [x, z, float(state["yaw"])],
            },
            shuttle_proxy,
            retain=True,
        )

    def move_process():
        time.sleep(move_duration)
        # The new location is decided when the request was received (see callback)
        publish_location()

    def move_callback(topic, client, message, properties):
        try:
            state["uuid"] = message.get("Uuid", "")
            target = message.get("Position") or message.get("position")
            label = _nearest_label(target, locations) or state["location"]
            state["location"] = label
            print(f"[{station_name}] MoveToPosition -> {label} (target={target})")
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
