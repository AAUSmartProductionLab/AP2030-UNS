#!/usr/bin/env python3
"""
Generate a JSON template for Resource AAS configuration.

Usage::

    cd Registration_Service
    python scripts/generate_json_template.py > example_resource.json

The template is built from ResourceTypeAAS class defaults with only
station-specific overrides applied — so it always reflects the current
model.  Update this script when template parameters change.
"""

import json
import sys
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, ".."))
sys.path.insert(0, os.path.join(_HERE, "..", "third_party", "aas_pydantic"))

from src.aas_idta.builder import generate_station_template


def main():
    template = generate_station_template(
        aas_id_short="YOUR_SYSTEM_AAS",
        aas_id="https://smartproductionlab.aau.dk/aas/YOUR_SYSTEM_AAS",
        asset_type="http://www.w3id.org/aau-ra/cssx#YourSystemType",
    )

    # Add metadata for users
    template["$schema"] = "https://smartproductionlab.aau.dk/schemas/resource_asset.json"
    template["$comment"] = (
        "Resource AAS configuration — generated from ResourceTypeAAS defaults. "
        "Fill in station-specific values; omitted fields use sensible defaults. "
        "Add station-specific MQTT actions under asset_interfaces_description."
    )

    json.dump(template, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
