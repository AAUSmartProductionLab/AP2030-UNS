"""Simulated IMA loading station with non-deterministic outcome.

The PDDL ``Loading`` action has ``oneOf`` effects:
    branch 0 (success): On(p, t) AND ProductAt(p, loc)
    branch 1 (drop):    NOT On(p, t)

Both outcomes are *planned* by the FOND policy -- a drop is not an
execution error, it is a valid branch. The branch indices match the
declaration order in ``imaLoadingSystem.yaml``.

Runtime contract: the response always reports ``State: SUCCESS`` (the
*action attempt* completed). The selected FOND branch is communicated
out-of-band in the ``Outcome`` integer field of the SUCCESS payload,
which ``ExecuteAction`` reads to pick which branch's symbolic effects
to apply to ``SymbolicState``. ``State: FAILURE`` is reserved for
genuine, unplanned failures (e.g. equipment fault) which are not
modelled in the FOND domain.
"""

import os
import random
import time

from services.stations.simple_station import run_simple_station


BASE_TOPIC = "NN/Nybrovej/InnoLab/Loading"
DROP_RATE = float(os.getenv("LOADING_FAILURE_RATE", "0.3"))
LOAD_DURATION = float(os.getenv("LOADING_DURATION", "2.0"))


def load_process():
    time.sleep(LOAD_DURATION)
    if random.random() < DROP_RATE:
        print(f"[Loading] FOND outcome: drop (rate={DROP_RATE}) -> Outcome=1")
        return {"State": "SUCCESS", "Outcome": 1, "Reason": "load_dropped"}
    print("[Loading] FOND outcome: success -> Outcome=0")
    return {"State": "SUCCESS", "Outcome": 0}


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
