import time
from services.stations.simple_station import run_simple_station


BASE_TOPIC = "NN/Nybrovej/InnoLab/Stoppering"


def stopper_process(duration=2.0):
    time.sleep(duration)


def main():
    run_simple_station(
        base_topic=BASE_TOPIC,
        station_name="Stoppering",
        command_label="Stoppering",
        config_path="syntegonStoppering.yaml",
        process_function=stopper_process,
    )


if __name__ == "__main__":
    main()
