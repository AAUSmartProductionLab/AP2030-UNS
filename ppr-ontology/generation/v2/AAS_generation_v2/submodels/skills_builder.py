"""SkillsSubmodelBuilderV2 — re-export.

The Skills submodel-level semanticId is corrected via SemanticIdFactoryV2's
override of `_SKILLS_SUBMODEL`. Per-skill URIs use `create_skill_semantic_id`
which is project-stable already.
"""
from generation.AAS_generation.submodels.skills_builder import (
    SkillsSubmodelBuilder as SkillsSubmodelBuilderV2,
)

__all__ = ["SkillsSubmodelBuilderV2"]
