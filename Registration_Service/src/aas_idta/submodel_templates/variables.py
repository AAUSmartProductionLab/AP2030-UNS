"""
Variables submodel — Pydantic model for asset variable definitions.

The Variables submodel contains named variable definitions. Each variable
has a semantic_id and optional InterfaceReference that maps it to an
AID property for live data via DataBridge/AIMC.

This is a custom (non-IDTA) submodel until an IDTA Variables template
is standardized. It follows the same structural pattern as generated
aas_pydantic templates.

Structure::

    Variables
    └── variables[]               (VariableItem)
        ├── semantic_id_param     (Property — ontology concept URI)
        └── interface_reference   (ReferenceElement → AID property)
"""

from __future__ import annotations

from typing import ClassVar, Dict
from aas_pydantic import (
    Submodel, SubmodelElementCollection, ContainerValue,
    Property
)

from ..constants import BASE_URL

SM_VARIABLES = f"{BASE_URL}/submodels/Variables/1/0"
VAR_INTERFACE_REF = f"{BASE_URL}/variables/InterfaceReference/1/0"
VAR_INTERFACE_NAME = f"{BASE_URL}/variables/InterfaceName/1/0"
VAR_INTERFACE_FIELD = f"{BASE_URL}/variables/InterfaceField/1/0"
VAR_ITEM = f"{BASE_URL}/variables/VariableItem/1/0"
VAR_SEMANTIC_ID = f"{BASE_URL}/variables/VariableSemanticId/1/0"


class VariableInterfaceReferenceValues(ContainerValue):
    """Children of a VariableInterfaceReference (field name == id_short)."""
    name: Property = Property(
        semantic_id=VAR_INTERFACE_NAME,
        description="Name of the AID property (e.g., 'StationState').",
    )
    field: Property = Property(
        semantic_id=VAR_INTERFACE_FIELD,
        description="Optional JSON field within the property's schema (e.g., 'State').",
    )


class VariableInterfaceReference(SubmodelElementCollection):
    """Reference to the AID property that provides live data for this variable."""
    semantic_id: str = VAR_INTERFACE_REF
    description: str = "Reference to the AID property and optional field within its schema."

    value: VariableInterfaceReferenceValues = VariableInterfaceReferenceValues()


class VariableItemValues(ContainerValue):
    """Children of a VariableItem (field name == id_short)."""
    semantic_id_param: Property = Property(
        semantic_id=VAR_SEMANTIC_ID,
        description="Semantic identifier (ontology concept URI) for this variable.",
    )
    interface_reference: VariableInterfaceReference = VariableInterfaceReference()


class VariableItem(SubmodelElementCollection):
    """A single variable definition."""
    semantic_id: str = VAR_ITEM
    description: str = "A named variable with semantic concept and optional live-data interface reference."

    value: VariableItemValues = VariableItemValues()


class Variables(Submodel):
    """
    Variables submodel — asset variable definitions.

    Contains named variables with semantic identifiers and optional
    references to AID properties for live-data mapping via AIMC/DataBridge.
    """
    semantic_id: str = SM_VARIABLES
    description: str = "Asset variable definitions with semantic concepts and live-data interface references."
    VERSION: ClassVar[str] = "1"
    REVISION: ClassVar[str] = "0"

    # Keys are variable id_shorts → dynamic map of VariableItem.
    submodel_element: Dict[str, VariableItem] = {}
