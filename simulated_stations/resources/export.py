#!/usr/bin/env python3
"""Regenerate the Resources the simulated stations register, from aas-model.

The stations publish these files as they are (with the AID base set to the
stack's broker or endpoint), so they do not import aas-model. Run after
changing a station's resource in aas-model::

    PYTHONPATH=../aas-model/src python resources/export.py    # from simulated_stations
"""

import json
from pathlib import Path

from aas_model import Resource
from aas_model.resource_instances import RESOURCE_FACTORIES

STATIONS = (
    "syntegonStoppering", "imaDispensing", "imaLoadingSystem", "cytivaCapping",
    "optimaUnloading", "omronCamera", "planarTable",
    "planarShuttle1", "planarShuttle2", "planarShuttle3",
)


def main() -> None:
    target = Path(__file__).resolve().parent
    for name in STATIONS:
        resource = RESOURCE_FACTORIES[name]()
        export = resource.model_dump_json(indent=2)
        # the registration service loads the export as a plain Resource
        loaded = Resource.model_validate_json(export)
        if json.loads(loaded.model_dump_json()) != json.loads(export):
            raise SystemExit(f"{name}: the registration service cannot load this export without loss")
        (target / f"{resource.id_short}.json").write_text(export + "\n", encoding="utf-8")
        print(f"wrote {resource.id_short}.json")


if __name__ == "__main__":
    main()
