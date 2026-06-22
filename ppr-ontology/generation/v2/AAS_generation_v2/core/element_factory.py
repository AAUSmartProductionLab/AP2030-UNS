"""AASElementFactoryV2 — v1 factory + a guard that fails loudly when a mandatory
SME is created without a `semantic_id`.

This turns "missing semanticId" from a silent bug into a build-time error so v2
can rely on serialization-by-semantic-ID. Any idShort listed in
`_REQUIRES_SEMANTIC_ID` MUST be created with a non-None `semantic_id` argument.
"""
from __future__ import annotations

from typing import Any, List, Optional

from basyx.aas import model

from generation.AAS_generation.core.element_factory import AASElementFactory


_REQUIRES_SEMANTIC_ID: set[str] = {
    "ManufacturerName",
    "ManufacturerProductDesignation",
    "ContactInformation",
    "OrderCodeOfManufacturer",
    "EndpointMetadata",
}


def _guard(id_short: str | None, semantic_id: Optional[model.ExternalReference]) -> None:
    if id_short in _REQUIRES_SEMANTIC_ID and semantic_id is None:
        raise ValueError(
            f"AAS_generation_v2: SME '{id_short}' requires a semanticId. "
            f"Pass semantic_id=SemanticIdFactoryV2().<XXX>. See semantic_ids.py."
        )


class AASElementFactoryV2(AASElementFactory):
    """Same API as v1 with mandatory-semanticId guard at the create boundary."""

    @staticmethod
    def create_property(
        id_short: str,
        value: Any,
        value_type: type = None,
        semantic_id: Optional[model.ExternalReference] = None,
        description: Optional[str] = None,
    ) -> model.Property:
        _guard(id_short, semantic_id)
        return AASElementFactory.create_property(
            id_short=id_short,
            value=value,
            value_type=value_type,
            semantic_id=semantic_id,
            description=description,
        )

    @staticmethod
    def create_multi_language_property(
        id_short: str,
        text: str,
        language: str = "en",
        semantic_id: Optional[model.ExternalReference] = None,
    ) -> model.MultiLanguageProperty:
        _guard(id_short, semantic_id)
        return AASElementFactory.create_multi_language_property(
            id_short=id_short, text=text, language=language, semantic_id=semantic_id,
        )

    @staticmethod
    def create_collection(
        id_short: str,
        elements: List[model.SubmodelElement],
        semantic_id: Optional[model.ExternalReference] = None,
        supplemental_semantic_ids: Optional[List[model.ExternalReference]] = None,
        description: Optional[str] = None,
    ) -> model.SubmodelElementCollection:
        _guard(id_short, semantic_id)
        return AASElementFactory.create_collection(
            id_short=id_short,
            elements=elements,
            semantic_id=semantic_id,
            supplemental_semantic_ids=supplemental_semantic_ids,
            description=description,
        )
