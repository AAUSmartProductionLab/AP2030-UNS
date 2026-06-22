"""Create invalid AAS test fixtures from the valid loading system AAS.

Each fixture triggers one or more specific SHACL constraint violations.
Output goes to aas_configs/tests/

Usage:
    python tools/create_invalid_test_fixtures.py
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

_WORKSPACE = Path(__file__).resolve().parent.parent
_VALID = _WORKSPACE / "aas_configs" / "generated" / "imaLoadingSystemAAS.aas.json"
_OUT = _WORKSPACE / "aas_configs" / "tests"
_OUT.mkdir(parents=True, exist_ok=True)


def load_valid() -> dict:
    return json.loads(_VALID.read_text(encoding="utf-8"))


def save(name: str, doc: dict, expected_violations: str) -> None:
    path = _OUT / name
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  {name}")
    print(f"    Expected: {expected_violations}")


def _remove_submodel_by_id_short(doc: dict, id_short: str) -> dict:
    """Remove a submodel (and its AAS reference) by idShort."""
    doc = copy.deepcopy(doc)

    # Remove from submodels list
    target_id = None
    doc["submodels"] = [
        sm for sm in doc.get("submodels", [])
        if not (sm.get("idShort") == id_short and (target_id := sm["id"]) is not None or sm.get("idShort") == id_short)
    ]
    # Also remove via actual id match — rebuild properly
    remaining_ids = {sm["id"] for sm in doc["submodels"]}

    # Remove corresponding ref from AAS shell submodels list
    for shell in doc.get("assetAdministrationShells", []):
        shell["submodels"] = [
            ref for ref in shell.get("submodels", [])
            if ref.get("keys", [{}])[0].get("value") in remaining_ids
        ]

    return doc


def _find_submodel(doc: dict, id_short: str) -> dict | None:
    for sm in doc.get("submodels", []):
        if sm.get("idShort") == id_short:
            return sm
    return None


def _remove_elements_by_id_short(elements: list, *id_shorts: str) -> list:
    """Remove top-level elements matching any of the given idShorts."""
    return [e for e in elements if e.get("idShort") not in id_shorts]


def _find_element(elements: list, id_short: str) -> dict | None:
    for e in elements:
        if e.get("idShort") == id_short:
            return e
    return None


# ─────────────────────────────────────────────────────────────────────────────

def make_missing_nameplate():
    """Drops the DigitalNameplate submodel entirely."""
    doc = _remove_submodel_by_id_short(load_valid(), "DigitalNameplate")
    save(
        "invalid_missing_nameplate.aas.json",
        doc,
        "AssetAdministrationShell missing arso:hasDigitalNameplateSubmodel (minCount 1)",
    )


def make_missing_hierarchical_structures():
    """Drops the HierarchicalStructures submodel entirely."""
    doc = _remove_submodel_by_id_short(load_valid(), "HierarchicalStructures")
    save(
        "invalid_missing_hierarchical_structures.aas.json",
        doc,
        "AssetAdministrationShell missing arso:hasHierarchicalStructuresSubmodel (minCount 1)",
    )


def make_nameplate_missing_mandatory_elements():
    """Removes ManufacturerName and URIOfTheProduct from the Nameplate submodel.

    Both are typed as arso:ManufacturerNameMLP / arso:URIOfTheProductProperty via
    their IRDI semantic IDs.  Their absence triggers:
      DigitalNameplateSubmodel: dash:hasValueWithClass arso:ManufacturerNameMLP (minCount 1)
      DigitalNameplateSubmodel: dash:hasValueWithClass arso:URIOfTheProductProperty (minCount 1)
    """
    doc = copy.deepcopy(load_valid())
    np = _find_submodel(doc, "DigitalNameplate")
    np["submodelElements"] = _remove_elements_by_id_short(
        np["submodelElements"], "ManufacturerName", "URIOfTheProduct"
    )
    save(
        "invalid_nameplate_missing_mandatory_elements.aas.json",
        doc,
        "DigitalNameplateSubmodel missing arso:ManufacturerNameMLP + arso:URIOfTheProductProperty",
    )


def make_nameplate_missing_address():
    """Removes the ContactInformation SMC from the Nameplate submodel.

    Triggers:
      DigitalNameplateSubmodel: dash:hasValueWithClass arso:AddressInformationSMC (minCount 1)
    """
    doc = copy.deepcopy(load_valid())
    np = _find_submodel(doc, "DigitalNameplate")
    np["submodelElements"] = _remove_elements_by_id_short(
        np["submodelElements"], "ContactInformation"
    )
    save(
        "invalid_nameplate_missing_address.aas.json",
        doc,
        "DigitalNameplateSubmodel missing arso:AddressInformationSMC (minCount 1)",
    )


def make_entry_node_empty_statements():
    """Empties the statements list of the EntryNode Entity in HierarchicalStructures.

    Triggers:
      EntryNodeEntity: dash:hasValueWithClass arso:NodeEntity in statements (minCount 1)
    """
    doc = copy.deepcopy(load_valid())
    hs = _find_submodel(doc, "HierarchicalStructures")
    for elem in hs.get("submodelElements", []):
        if elem.get("idShort") == "EntryNode":
            elem["statements"] = []
            break
    save(
        "invalid_entry_node_empty_statements.aas.json",
        doc,
        "EntryNodeEntity missing arso:NodeEntity in statements (minCount 1)",
    )


def make_aid_empty_interface():
    """Empties the AID submodel's submodelElements list.

    The AIDSubmodel shape requires at least one arso:InterfaceSMC child
    (dash:hasValueWithClass arso:InterfaceSMC; minCount 1).  Removing all
    elements triggers that constraint.
    """
    doc = copy.deepcopy(load_valid())
    aid = _find_submodel(doc, "AID")
    if aid:
        aid["submodelElements"] = []
    save(
        "invalid_aid_empty_interface.aas.json",
        doc,
        "AIDSubmodel missing arso:InterfaceSMC (dash:hasValueWithClass minCount 1)",
    )


def make_address_missing_city():
    """Removes CityTown from the ContactInformation SMC.

    Triggers:
      AddressInformationSMC: dash:hasValueWithClass arso:AddressCityTownMLP (minCount 1)
    """
    doc = copy.deepcopy(load_valid())
    np = _find_submodel(doc, "DigitalNameplate")
    contact_smc = _find_element(np.get("submodelElements", []), "ContactInformation")
    if contact_smc:
        contact_smc["value"] = _remove_elements_by_id_short(
            contact_smc.get("value", []), "CityTown"
        )
    save(
        "invalid_address_missing_city.aas.json",
        doc,
        "AddressInformationSMC missing arso:AddressCityTownMLP (dash:hasValueWithClass)",
    )


def make_skills_without_aid():
    """Removes the AID submodel while keeping the Skills (and Capabilities) submodels.

    R5 (arso-rules.shacl.ttl): Skills submodel present => AID submodel present.
    Skills reference AID interfaces; without AID those references are unresolvable.
    """
    doc = _remove_submodel_by_id_short(load_valid(), "AID")
    save(
        "invalid_skills_without_aid.aas.json",
        doc,
        "R5: Skills submodel present but AID submodel absent (cross-submodel dependency)",
    )


def make_capabilities_missing_capability_element():
    """Removes the Capability element from inside the CapabilityContainer.

    The Capabilities submodel has a nested structural dependency chain:
      CapabilitiesSubmodel -> CapabilitySetSMC -> CapabilityContainerSMC -> CapabilityElement

    The outer structure (Set and Container SMCs) is kept intact; only the
    leaf arso:CapabilityElement (modelType=Capability) is removed.

    Triggers:
      CapabilityContainerSMC: dash:hasValueWithClass arso:CapabilityElement (minCount 1)
    """
    doc = copy.deepcopy(load_valid())
    caps = _find_submodel(doc, "Capabilities")
    cap_set = _find_element(caps.get("submodelElements", []), "CapabilitySet")
    if cap_set:
        for container in cap_set.get("value", []):
            container["value"] = [
                e for e in container.get("value", [])
                if e.get("modelType") != "Capability"
            ]
    save(
        "invalid_capabilities_missing_capability_element.aas.json",
        doc,
        "CapabilityContainerSMC missing arso:CapabilityElement (nested dependency chain)",
    )


if __name__ == "__main__":
    print(f"Writing invalid test fixtures to {_OUT}/")
    make_missing_nameplate()
    make_missing_hierarchical_structures()
    make_nameplate_missing_mandatory_elements()
    make_nameplate_missing_address()
    make_entry_node_empty_statements()
    make_aid_empty_interface()
    make_address_missing_city()
    make_skills_without_aid()
    make_capabilities_missing_capability_element()
    print("Done.")
