"""HierarchicalStructuresSubmodelBuilderV2 — re-export.

v1 builder already attaches IDTA-aligned ArcheType / EntryNode semanticIds; the
submodel-level URL is corrected automatically by SemanticIdFactoryV2's override
of `_HIERARCHICAL_STRUCTURES`.
"""
from generation.AAS_generation.submodels.hierarchical_structures_builder import (
    HierarchicalStructuresSubmodelBuilder as HierarchicalStructuresSubmodelBuilderV2,
)

__all__ = ["HierarchicalStructuresSubmodelBuilderV2"]
