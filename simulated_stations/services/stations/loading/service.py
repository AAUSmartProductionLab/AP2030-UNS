import time
from services.stations.simple_station import run_simple_station


BASE_TOPIC = "NN/Nybrovej/InnoLab/Loading"


def load_process(duration=2.0):
    time.sleep(duration)


def main():
    run_simple_station(
        base_topic=BASE_TOPIC,
        station_name="Loading",
        command_label="Loading",
        config_path="imaLoadingSystem.yaml",
        process_function=load_process,
    )


if __name__ == "__main__":
    main()
