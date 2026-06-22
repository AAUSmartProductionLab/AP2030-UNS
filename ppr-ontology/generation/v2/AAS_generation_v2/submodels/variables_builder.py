"""VariablesSubmodelBuilderV2 — re-export.

The OperationalData (Variables) submodel-level semanticId is corrected via
SemanticIdFactoryV2's override of `_VARIABLES_SUBMODEL`.
"""
from generation.AAS_generation.submodels.variables_builder import (
    VariablesSubmodelBuilder as VariablesSubmodelBuilderV2,
)

__all__ = ["VariablesSubmodelBuilderV2"]
