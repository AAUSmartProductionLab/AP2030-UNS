"""AASGenerator for v2 — same public API as v1, swaps in v2 factories/builders.

The pipeline calls `AASGenerator(config_path, base_url_override=...).generate_system(...)`
so we keep that signature and only override `_initialize_builders` to wire the
v2 implementations. v1 `AASGenerator` does the heavy orchestration (config
loading, ontology guidance, object-store assembly, JSON serialization).
"""
from __future__ import annotations

from generation.AAS_generation.cli.generate_aas import AASGenerator as _V1Generator
from generation.AAS_generation.submodels import (
    ProcessInformationSubmodelBuilder,
    RequiredCapabilitiesSubmodelBuilder,
    PolicySubmodelBuilder,
)

from ..core import (
    AASBuilderV2,
    AASElementFactoryV2,
    SchemaHandler,
    SemanticIdFactoryV2,
)
from ..submodels import (
    AssetInterfacesBuilderV2,
    CapabilitiesSubmodelBuilderV2,
    DigitalNameplateSubmodelBuilderV2,
    HierarchicalStructuresSubmodelBuilderV2,
    ParametersSubmodelBuilderV2,
    SkillsSubmodelBuilderV2,
    VariablesSubmodelBuilderV2,
)


class AASGenerator(_V1Generator):
    """v2 AAS generator — drop-in replacement for v1's `AASGenerator`."""

    def _initialize_builders(self) -> None:
        self.schema_handler = SchemaHandler()
        self.element_factory = AASElementFactoryV2()
        self.semantic_factory = SemanticIdFactoryV2()

        self.aas_builder = AASBuilderV2(self.base_url)

        self.nameplate_builder = DigitalNameplateSubmodelBuilderV2(
            self.base_url, self.semantic_factory, self.element_factory
        )
        self.asset_interfaces_builder = AssetInterfacesBuilderV2(
            self.base_url, self.semantic_factory, self.element_factory
        )
        self.variables_builder = VariablesSubmodelBuilderV2(
            self.base_url, self.semantic_factory, self.element_factory, self.schema_handler
        )
        self.skills_builder = SkillsSubmodelBuilderV2(
            self.base_url,
            self.delegation_base_url,
            self.semantic_factory,
            self.element_factory,
            self.schema_handler,
        )
        self.parameters_builder = ParametersSubmodelBuilderV2(
            self.base_url, self.semantic_factory, self.element_factory, self.schema_handler
        )
        self.hierarchical_structures_builder = HierarchicalStructuresSubmodelBuilderV2(
            self.base_url, self.semantic_factory, self.element_factory
        )
        self.capabilities_builder = CapabilitiesSubmodelBuilderV2(
            self.base_url, self.semantic_factory, self.element_factory
        )

        # Process AAS builders are unchanged in v2 — they don't carry IDTA semanticIds.
        self.process_info_builder = ProcessInformationSubmodelBuilder(
            self.base_url, self.semantic_factory, self.element_factory
        )
        self.required_capabilities_builder = RequiredCapabilitiesSubmodelBuilder(
            self.base_url, self.semantic_factory, self.element_factory
        )
        self.policy_builder = PolicySubmodelBuilder(
            self.base_url, self.semantic_factory, self.element_factory
        )
