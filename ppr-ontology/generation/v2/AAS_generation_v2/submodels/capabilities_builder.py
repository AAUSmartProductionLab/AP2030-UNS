"""CapabilitiesSubmodelBuilderV2 — re-export.

The submodel-level semanticId is corrected via SemanticIdFactoryV2's override of
`_CAPABILITIES_SUBMODEL` (now `https://admin-shell.io/idta/CapabilityDescription/1/0`).
v1's inner CAPABILITY_SET / CAPABILITY_CONTAINER / CAPABILITY URIs are non-IDTA but
the CSSx_AAS ontology doesn't constrain those by semanticId — only the submodel
type, CapabilitySet presence, and Capability semanticId presence matter.
"""
from generation.AAS_generation.submodels.capabilities_builder import (
    CapabilitiesSubmodelBuilder as CapabilitiesSubmodelBuilderV2,
)

__all__ = ["CapabilitiesSubmodelBuilderV2"]
