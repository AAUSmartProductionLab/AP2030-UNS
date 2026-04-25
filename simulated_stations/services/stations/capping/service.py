"""Simulated capping station (Cytiva)."""

import time
from services.stations.simple_station import run_simple_station


BASE_TOPIC = "NN/Nybrovej/InnoLab/Capping"


def cap_process(duration=2.0):
    time.sleep(duration)


def main():
    run_simple_station(
        base_topic=BASE_TOPIC,
        station_name="Capping",
        command_label="Capping",
        config_path="cytivaCapping.yaml",
        process_function=cap_process,
    )


if __name__ == "__main__":
    main()
