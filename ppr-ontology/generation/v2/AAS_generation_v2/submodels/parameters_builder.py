"""ParametersSubmodelBuilderV2 — re-export.

The Parameters submodel-level semanticId is corrected via SemanticIdFactoryV2's
override of `_PARAMETERS_SUBMODEL`.
"""
from generation.AAS_generation.submodels.parameters_builder import (
    ParametersSubmodelBuilder as ParametersSubmodelBuilderV2,
)

__all__ = ["ParametersSubmodelBuilderV2"]
