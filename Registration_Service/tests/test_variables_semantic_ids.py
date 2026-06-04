from __future__ import annotations

import os
import sys

from basyx.aas import model

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.aas_generation import AASElementFactory, SchemaHandler, SemanticIdFactory
from src.aas_generation.submodels.variables_builder import VariablesSubmodelBuilder


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


def test_variables_builder_propagates_semantic_id_to_selected_schema_field():
    builder = VariablesSubmodelBuilder(
        base_url="https://smartproductionlab.aau.dk",
        semantic_factory=SemanticIdFactory(),
        element_factory=AASElementFactory(),
        schema_handler=SchemaHandler(),
    )

    config = {
        "Variables": [
            {
                "key": "PackMLState",
                "semanticId": "https://w3id.org/2026/apex/semantic/state/operational",
                "InterfaceReference": {
                    "Name": "StationState",
                    "Field": "State",
                },
            },
            {
                "key": "PositionX",
                "semanticId": "https://w3id.org/2026/apex/semantic/position/x",
                "InterfaceReference": {
                    "Name": "Location",
                    "Field": "X",
                },
            },
        ]
    }

    properties = [
        {
            "name": "StationState",
            "schema": "https://aausmartproductionlab.github.io/AP2030-UNS/MQTTSchemas/stationState.schema.json",
        },
        {
            "name": "Location",
            "schema": "https://aausmartproductionlab.github.io/AP2030-UNS/MQTTSchemas/positionStamped.schema.json",
        },
    ]

    submodel = builder.build(system_id="test-system", config=config, properties=properties)

    packml = _find_collection(submodel, "PackMLState")
    packml_state_property = _find_property(packml, "State")
    assert _semantic_id_value(packml_state_property.semantic_id) == "https://w3id.org/2026/apex/semantic/state/operational"

    position_x = _find_collection(submodel, "PositionX")
    x_property = _find_property(position_x, "X")
    assert _semantic_id_value(x_property.semantic_id) == "https://w3id.org/2026/apex/semantic/position/x"
