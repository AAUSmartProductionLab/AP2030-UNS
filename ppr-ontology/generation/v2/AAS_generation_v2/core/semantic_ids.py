"""SemanticIdFactoryV2 — IDTA-aligned semanticIds, subclasses v1.

Strategy: subclass `SemanticIdFactory` and override the private constants the v1
factory uses internally. v1's `@property` methods read `self._FOO`, so they
automatically pick up the overrides at runtime. New IDs (e.g., NP_MANUFACTURER_NAME)
are added as fresh properties.

The exact values here are the single source of truth and must match the lookup
tables in `tools/aas_to_rdf.py`.
"""
from __future__ import annotations

from basyx.aas import model

from generation.AAS_generation.core.semantic_ids import SemanticIdFactory


# String constants exported separately so tools/aas_to_rdf.py can import them
# without instantiating the factory.

# --- Submodel-level (IDTA where applicable, project-stable otherwise) ---
SM_NAMEPLATE                = "https://admin-shell.io/zvei/nameplate/2/0/Nameplate"
SM_HIERARCHICAL_STRUCTURES  = "https://admin-shell.io/idta/HierarchicalStructures/1/0/Submodel"
SM_ASSET_INTERFACES         = "https://admin-shell.io/idta/AssetInterfacesDescription/1/0/Submodel"
SM_CAPABILITIES             = "https://admin-shell.io/idta/CapabilityDescription/1/0"
SM_SKILLS                   = "https://smartproductionlab.aau.dk/CSSx/Skills/1/0/Submodel"
SM_OPERATIONAL_DATA         = "https://smartproductionlab.aau.dk/CSSx/OperationalData/1/0/Submodel"
SM_PARAMETERS               = "https://smartproductionlab.aau.dk/CSSx/Parameters/1/0/Submodel"

# --- Mandatory Nameplate SMEs (per IDTA 02006) ---
NP_MANUFACTURER_NAME                = "https://admin-shell.io/zvei/nameplate/1/0/Nameplate/ManufacturerName"
NP_MANUFACTURER_PRODUCT_DESIGNATION = "https://admin-shell.io/zvei/nameplate/1/0/Nameplate/ManufacturerProductDesignation"
NP_CONTACT_INFORMATION              = "https://admin-shell.io/zvei/nameplate/1/0/Nameplate/ContactInformation"
NP_ORDER_CODE_OF_MANUFACTURER       = "https://admin-shell.io/zvei/nameplate/1/0/Nameplate/OrderCodeOfManufacturer"

# --- Hierarchical Structures SMEs ---
HS_ARCHETYPE  = "https://admin-shell.io/idta/HierarchicalStructures/ArcheType/1/0"
HS_ENTRY_NODE = "https://admin-shell.io/idta/HierarchicalStructures/EntryNode/1/0"

# --- AID SMEs (Interface and InteractionMetadata are correct in v1; EndpointMetadata is missing) ---
AID_INTERFACE             = "https://admin-shell.io/idta/AssetInterfacesDescription/1/0/Interface"
AID_ENDPOINT_METADATA     = "https://admin-shell.io/idta/AssetInterfacesDescription/1/0/EndpointMetadata"
AID_INTERACTION_METADATA  = "https://admin-shell.io/idta/AssetInterfacesDescription/1/0/InteractionMetadata"


class SemanticIdFactoryV2(SemanticIdFactory):
    """Drop-in replacement for v1 SemanticIdFactory with IDTA-aligned IDs.

    Override strategy: re-bind the private class constants the v1 properties read
    via `self._FOO`. Python's MRO does the rest — no method overrides needed for
    the corrected URLs. New IDs ship as additional properties below.
    """

    # --- Override broken / non-IDTA values from v1 ---
    _DIGITAL_NAMEPLATE_SUBMODEL = SM_NAMEPLATE                # was "https://admin-shell.io/IDTA 02006-3-0" (space)
    _HIERARCHICAL_STRUCTURES    = SM_HIERARCHICAL_STRUCTURES  # was 1/1, IDTA published is 1/0
    _CAPABILITIES_SUBMODEL      = SM_CAPABILITIES             # was smartfactory.de
    _SKILLS_SUBMODEL            = SM_SKILLS                   # was smartfactory.de
    _VARIABLES_SUBMODEL         = SM_OPERATIONAL_DATA         # project-stable namespace
    _PARAMETERS_SUBMODEL        = SM_PARAMETERS               # project-stable namespace

    # --- New constants (no v1 equivalent) ---
    _NP_MANUFACTURER_NAME                = NP_MANUFACTURER_NAME
    _NP_MANUFACTURER_PRODUCT_DESIGNATION = NP_MANUFACTURER_PRODUCT_DESIGNATION
    _NP_CONTACT_INFORMATION              = NP_CONTACT_INFORMATION
    _NP_ORDER_CODE_OF_MANUFACTURER       = NP_ORDER_CODE_OF_MANUFACTURER
    _AID_ENDPOINT_METADATA               = AID_ENDPOINT_METADATA

    # --- New properties for the constants above ---
    @property
    def NP_MANUFACTURER_NAME(self) -> model.ExternalReference:
        return self.create_external_reference(self._NP_MANUFACTURER_NAME)

    @property
    def NP_MANUFACTURER_PRODUCT_DESIGNATION(self) -> model.ExternalReference:
        return self.create_external_reference(self._NP_MANUFACTURER_PRODUCT_DESIGNATION)

    @property
    def NP_CONTACT_INFORMATION(self) -> model.ExternalReference:
        return self.create_external_reference(self._NP_CONTACT_INFORMATION)

    @property
    def NP_ORDER_CODE_OF_MANUFACTURER(self) -> model.ExternalReference:
        return self.create_external_reference(self._NP_ORDER_CODE_OF_MANUFACTURER)

    @property
    def AID_ENDPOINT_METADATA(self) -> model.ExternalReference:
        return self.create_external_reference(self._AID_ENDPOINT_METADATA)
