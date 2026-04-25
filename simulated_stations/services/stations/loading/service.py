"""Simulated IMA loading station with non-deterministic outcome.

The PDDL ``Loading`` action has ``oneOf`` effects (success vs failure).
This simulator samples the actual outcome at runtime: with probability
``LOADING_FAILURE_RATE`` (default ``0.3``) the load command reports
FAILURE so the FOND policy must take its retry branch.
"""

import os
import random
import time

from services.stations.simple_station import run_simple_station


BASE_TOPIC = "NN/Nybrovej/InnoLab/Loading"
FAILURE_RATE = float(os.getenv("LOADING_FAILURE_RATE", "0.3"))
LOAD_DURATION = float(os.getenv("LOADING_DURATION", "2.0"))


def load_process():
    time.sleep(LOAD_DURATION)
    if random.random() < FAILURE_RATE:
        print(f"[Loading] FOND outcome: failure (rate={FAILURE_RATE})")
        return {"State": "FAILURE", "Reason": "load_dropped"}
    print("[Loading] FOND outcome: success")
    return {"State": "SUCCESS"}


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
