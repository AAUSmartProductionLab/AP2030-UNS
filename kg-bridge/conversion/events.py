from __future__ import annotations

from enum import Enum
from typing import Annotated, Union

from pydantic import BaseModel, Field, TypeAdapter

from py_aas_rdf.models.asset_administraion_shell import AssetAdministrationShell
from py_aas_rdf.models.asset_information import AssetInformation
from py_aas_rdf.models.reference import Reference
from py_aas_rdf.models.submodel import Submodel
from py_aas_rdf.models.submodel_element_choice import SubmodelElementChoice


class AasEventType(str, Enum):
    AAS_CREATED = "AAS_CREATED"
    AAS_UPDATED = "AAS_UPDATED"
    AAS_DELETED = "AAS_DELETED"
    SM_REF_ADDED = "SM_REF_ADDED"
    SM_REF_DELETED = "SM_REF_DELETED"
    ASSET_INFORMATION_SET = "ASSET_INFORMATION_SET"


class SubmodelEventType(str, Enum):
    SM_CREATED = "SM_CREATED"
    SM_UPDATED = "SM_UPDATED"
    SM_DELETED = "SM_DELETED"
    SME_UPDATED = "SME_UPDATED"
    SME_CREATED = "SME_CREATED"
    SME_DELETED = "SME_DELETED"


class AasEvent(BaseModel):
    type: AasEventType
    id: str
    submodelId: str | None = None
    aas: AssetAdministrationShell | None = None
    reference: Reference | None = None
    assetInformation: AssetInformation | None = None


class SubmodelEvent(BaseModel):
    type: SubmodelEventType
    id: str
    submodel: Submodel | None = None
    smElement: SubmodelElementChoice | None = None
    smElementPath: str | None = None


KafkaEvent = Annotated[Union[AasEvent, SubmodelEvent], Field(discriminator="type")]

SubmodelEvent.model_rebuild()
AasEvent.model_rebuild()

_AAS_EVENT_ADAPTER = TypeAdapter(AasEvent)
_SUBMODEL_EVENT_ADAPTER = TypeAdapter(SubmodelEvent)


def _topic_is_aas(topic: str) -> bool:
    lowered = (topic or "").lower()
    return lowered == "aas-events" or lowered.endswith(".aas-events") or lowered.endswith("/aas-events")


def _topic_is_submodel(topic: str) -> bool:
    lowered = (topic or "").lower()
    return (
        lowered == "submodel-events"
        or lowered.endswith(".submodel-events")
        or lowered.endswith("/submodel-events")
    )


def parse_event(payload: dict, topic: str) -> AasEvent | SubmodelEvent:
    if _topic_is_aas(topic):
        return _AAS_EVENT_ADAPTER.validate_python(payload)

    if _topic_is_submodel(topic):
        return _SUBMODEL_EVENT_ADAPTER.validate_python(payload)

    event_type = str(payload.get("type", "")).upper()
    if event_type.startswith("AAS_") or event_type.startswith("SM_REF"):
        return _AAS_EVENT_ADAPTER.validate_python(payload)
    if event_type.startswith("SM_") or event_type.startswith("SME_"):
        return _SUBMODEL_EVENT_ADAPTER.validate_python(payload)

    raise ValueError(f"Unsupported topic '{topic}' and unknown event type '{event_type}'")
