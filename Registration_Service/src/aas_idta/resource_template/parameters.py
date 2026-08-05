from typing import Literal, Dict
from aas_pydantic import Property, SubmodelElement, ContainerValue
from ..submodel_templates.parameters import ParameterItem, Parameters
from ..constants import BASE_URL


PARAM_POSITION = f"{BASE_URL}/parameters/Position/1/0"
PARAM_POSITION_COORDINATE = f"{BASE_URL}/parameters/Position/Coordinate/1/0"


class CoordinateValue(Property):
    """Typed Property for a single position coordinate (value_type=xs:float).

    The id_short matches the values-model field it lives under (x/y/yaw).
    """
    id_short: Literal["x", "y", "yaw"] = "x"
    semantic_id: str = PARAM_POSITION_COORDINATE
    description: str = "The value of one coordinate part of a position"
    value_type: str = "xs:float"
    value: str = "0.0"


class PositionValues(ContainerValue):
    """Children of a Position (x / y / yaw — field name == id_short).

    Override any coordinate in JSON: ``{"value": {"x": {...}}}`` — omitted
    coordinates keep their defaults.
    """
    x: CoordinateValue = CoordinateValue(value="480.0")
    y: CoordinateValue = CoordinateValue(value="120.0")
    yaw: CoordinateValue = CoordinateValue(value="0.0")


class Position(ParameterItem):
    """2D position and orientation.

    Children live in a typed values model with x, y, yaw defaults.
    """
    semantic_id: str = PARAM_POSITION
    id_short: str = "Location"
    description: str = "2D position with X, Y coordinates and Yaw orientation."

    value: PositionValues = PositionValues()

class ResourceParameters(Parameters):
    """
        The parameter SM for a generic Resource
    """
    id_short: str = "Parameters"
    submodel_element: Dict[str, ParameterItem] = {
        "Location": Position()
    }
