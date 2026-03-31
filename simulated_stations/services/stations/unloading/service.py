import time
from services.stations.simple_station import run_simple_station


BASE_TOPIC = "NN/Nybrovej/InnoLab/Unloading"


def unload_process(duration=2.0):
    time.sleep(duration)


def main():
    run_simple_station(
        base_topic=BASE_TOPIC,
        station_name="Unload",
        command_label="Unloading",
        config_path="optimaUnloading.yaml",
        process_function=unload_process,
    )


if __name__ == "__main__":
    main()
