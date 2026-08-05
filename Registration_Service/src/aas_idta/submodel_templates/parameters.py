"""
Parameters submodel — Pydantic model for asset parameter definitions.

The Parameters submodel defines hierarchical key-value parameters with
semantic identifiers. Parameters are similar to Variables but represent
static or configurable values (e.g., physical location, calibration data)
rather than live telemetry.

This is a custom (non-IDTA) submodel. It follows the same structural
pattern as generated aas_pydantic templates.

Structure::

    Parameters
    └── parameters[]             (ParameterItem — hierarchical, can nest)
        ├── semantic_id          (SMC semantic id — ontology concept URI)
        └── children[]           (ParameterItem — recursive nesting)
            └── properties[]     (Property — leaf values)
"""

from __future__ import annotations

from typing import ClassVar, Dict
from aas_pydantic import (
    Submodel, SubmodelElement, SubmodelElementCollection,
    Property,
)

from ..constants import BASE_URL

SM_PARAMETERS = f"{BASE_URL}/submodels/Parameters/1/0"
PARAM_ITEM = f"{BASE_URL}/parameters/ParameterItem/1/0"
PARAM_VALUE = f"{BASE_URL}/parameters/ParamValue/1/0"

"""Generic Template Definition"""

class ParameterItem(SubmodelElementCollection):
    """
    A parameter definition — can contain nested sub-parameters or leaf values.

    Parameters use semantic_id (SMC-level) for ontology alignment and can nest
    recursively. Leaf values are Property elements (string, number, boolean).
    The ``value`` dict holds both nested ParameterItems and leaf Property
    values.
    """
    model_config = {"validate_default": True}
    semantic_id: str = PARAM_ITEM
    description: str = "A named parameter with optional semanticId and potential nested children."

    # Keys are child id_shorts → heterogeneous children.
    value: Dict[str, SubmodelElement] = {}

class Parameters(Submodel):
    """
    Parameters submodel — hierarchical asset parameter definitions.

    Contains static/configurable parameters with semantic identifiers.
    Supports recursive nesting (e.g., Location → Position → {X, Y, Yaw}).
    """
    semantic_id: str = SM_PARAMETERS
    description: str = "Hierarchical asset parameter definitions with semantic identifiers."
    VERSION: ClassVar[str] = "1"
    REVISION: ClassVar[str] = "0"

    # Keys are parameter id_shorts → specialized container.
    submodel_element: Dict[str, ParameterItem] = {}
