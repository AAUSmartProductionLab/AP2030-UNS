"""Variables submodel — semantic_id propagation tests (aas_idta flow).

Verifies that the Variables submodel built from a ResourceTypeAAS config
carries the ontology semantic URI (``semantic_id_param``) on each variable,
and that DataBridge property mappings propagate variables → MQTT topic /
schema field.
"""

from __future__ import annotations

import os
import sys

from basyx.aas import model

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "third_party", "aas_pydantic")))

from src.aas_idta.builder import build_from_json  # noqa: E402
from src.config_parser import (  # noqa: E402
    parse_config_file,
    extract_databridge_property_mappings,
    _extract_variables,
)

CONFIG_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "AASDescriptions",
                 "Resource", "configs", "syntegonStoppering.json")
)


def _find_collection(submodel: model.Submodel, id_short: str) -> model.SubmodelElementCollection:
    for element in submodel.submodel_element:
        if isinstance(element, model.SubmodelElementCollection) and element.id_short == id_short:
            return element
    raise AssertionError(f"Variable collection not found: {id_short}")


def _find_property(collection: model.SubmodelElementCollection, id_short: str) -> model.Property:
    for element in collection.value:
        if isinstance(element, model.Property) and element.id_short == id_short:
            return element
    raise AssertionError(f"Property not found: {collection.id_short}.{id_short}")


def _semantic_id_value(ref: model.ExternalReference | None) -> str | None:
    if ref is None:
        return None
    if not ref.key:
        return None
    return ref.key[0].value


def _find_variables_submodel(store) -> model.Submodel:
    for obj in store:
        submodels = obj.submodel if hasattr(obj, "submodel") else [obj]
        for sm in submodels:
            if isinstance(sm, model.Submodel) and sm.id_short == "Variables":
                return sm
    raise AssertionError("Variables submodel not found in store")


def test_variables_semantic_id_propagates_to_built_submodel():
    store = build_from_json(CONFIG_PATH)
    variables_sm = _find_variables_submodel(store)

    packml = _find_collection(variables_sm, "PackMLState")
    packml_semantic = _find_property(packml, "semantic_id_param")
    assert packml_semantic.value == "https://w3id.org/2026/apex/semantic/state/operational"

    occupation = _find_collection(variables_sm, "OccupationState")
    occupation_semantic = _find_property(occupation, "semantic_id_param")
    assert occupation_semantic.value == "https://w3id.org/2026/apex/semantic/state/occupied"


def test_variables_extractor_returns_semantic_ids():
    asset = parse_config_file(CONFIG_PATH)
    variables = {v["name"]: v for v in _extract_variables(asset)}

    assert set(variables) == {"PackMLState", "OccupationState"}
    assert variables["PackMLState"]["semantic_id"] == "https://w3id.org/2026/apex/semantic/state/operational"
    assert variables["PackMLState"]["interface_reference"] == "StationState"
    assert variables["PackMLState"]["field"] == "State"
    assert variables["OccupationState"]["semantic_id"] == "https://w3id.org/2026/apex/semantic/state/occupied"
    assert variables["OccupationState"]["field"] == "ProcessQueue"


def test_databridge_property_mappings_propagate_schema_and_field():
    asset = parse_config_file(CONFIG_PATH)
    mappings = extract_databridge_property_mappings(asset)

    by_name = {m["variable_name"]: m for m in mappings}
    assert "PackMLState" in by_name
    assert by_name["PackMLState"]["mqtt_topic"].endswith("/DATA/State")
    assert by_name["PackMLState"]["mqtt_field"] == "State"
    assert by_name["PackMLState"]["schema_url"].endswith("stationState.schema.json")

    assert "OccupationState" in by_name
    assert by_name["OccupationState"]["mqtt_field"] == "ProcessQueue"
