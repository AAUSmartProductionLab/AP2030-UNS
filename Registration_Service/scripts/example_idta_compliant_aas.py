#!/usr/bin/env python3
"""
Example: Build a compliant AAS using generated IDTA templates.

Key design: every leaf AAS element (Property, ReferenceElement, etc.) is a
proper Pydantic model with pre-filled semantic_id, description, and qualifiers.
You only set the runtime *value* — metadata flows from the template default.

Two patterns are shown:
  1. Mutate after construction  (accept defaults, set .value)
  2. Construct with model instances  (explicit but self-contained)

Usage:
    cd Registration_Service
    python scripts/example_idta_compliant_aas.py
"""

import os
import sys
import warnings

warnings.filterwarnings("ignore")

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "third_party", "aas_pydantic"))

from aas_pydantic.submodel_templates.nameplate import Nameplate
from aas_pydantic.submodel_templates.capability_description import (
    CapabilityDescription,
    CapabilityContainer,
    CapabilityContainerValues,
    CapabilitySet,
    CapabilitySetValues,
)
from aas_pydantic.submodel_templates.control_component_instance import (
    ControlComponentInstance,
    Endpoint,
    EndpointValues,
    Skill,
    SkillValues,
)
from aas_pydantic import (
    Capability,
    ExternalReference,
    Key,
    ModelReference,
    Property,
    RelationshipElement,
    convert_model_to_submodel,
)

BASE_URL = "https://smartproductionlab.aau.dk"
ASSET_ID = "syntegonStopperingSystemAAS"


def sm_id(name: str) -> str:
    return f"{BASE_URL}/submodels/instances/{ASSET_ID}/{name}"


# ═══════════════════════════════════════════════════════════════════════
# Pattern 1: Mutate after construction
#   Accept all template defaults (metadata is pre-filled), then set
#   only the runtime values on the leaf models.  Children live in the
#   ``submodel_element`` / ``value`` dicts keyed by id_short.
# ═══════════════════════════════════════════════════════════════════════

# ── Nameplate ──
nameplate = Nameplate(id_short="Nameplate", id=sm_id("Nameplate"))
# Set runtime values (metadata already on the Property/File defaults)
nameplate.submodel_element.u_r_i_of_the_product.value = (
    "https://example.com/products/SYN-SS-001"
)
nameplate.submodel_element.manufacturer_name.value = {"en": "Syntegon Technology GmbH"}
nameplate.submodel_element.manufacturer_product_designation.value = {
    "en": "Stoppering System 2024"
}
nameplate.submodel_element.order_code_of_manufacturer.value = "SYN-SS-2024-001"
nameplate.submodel_element.serial_number.value = "SYN-SS-2024-001"
nameplate.submodel_element.year_of_construction.value = "2024"
nameplate.submodel_element.manufacturer_product_type.value = (
    "Pharmaceutical Stoppering Station"
)
nameplate.submodel_element.country_of_origin.value = "DE"
# arbitrary_property is a multi-cardinality map
nameplate.submodel_element.asset_specific_properties.value.arbitrary_property = {
    "arbitrary_property": Property(value="ProcessCell: InnoLab Line 1")
}

# ── Capability Description ──
capability_desc = CapabilityDescription(
    id_short="CapabilityDescription",
    id=sm_id("CapabilityDescription"),
)
# capability_set / capability_container are multi-cardinality maps → build the
# nested structure explicitly.
cc_values = CapabilityContainerValues()
cc_values.capability.semantic_id = f"{BASE_URL}/capabilities/Stoppering"
cc_values.capability_comment.value = {
    "en": "Places rubber stoppers into vials at up to 120 ppm"
}
# capability_realized_by is a multi-cardinality map
realized_by = cc_values.capability_relations.value.capability_realized_by[
    "capability_realized_by"
] = RelationshipElement(
    first=ExternalReference(
        key=(Key(type_="GlobalReference", value=sm_id("CapabilityDescription")),)
    ),
    second=ExternalReference(
        key=(Key(type_="GlobalReference", value=sm_id("ControlComponentInstance")),)
    ),
)
capability_desc.submodel_element.capability_set = {
    "capability_set": CapabilitySet(
        value=CapabilitySetValues(
            capability_container={
                "capability_container": CapabilityContainer(value=cc_values)
            }
        )
    )
}

# ── Control Component Instance (Pattern 2: explicit model instances) ──
cci = ControlComponentInstance(
    id_short="ControlComponentInstance",
    id=sm_id("ControlComponentInstance"),
)
# Mutate nested ReferenceElement values
cci.submodel_element.type.value = ModelReference(
    key=(Key(type_="AssetAdministrationShell", value=sm_id("ControlComponentType")),)
)
# endpoint / skill are multi-cardinality maps (name → element)
endpoint_values = EndpointValues()
endpoint_values.interface_reference.value = ExternalReference(
    key=(Key(
        type_="GlobalReference",
        value="https://admin-shell.io/idta/ControlComponent/Interface/MQTT/1/0",
    ),)
)
endpoint_values.endpoint_reference.value = ExternalReference(
    key=(Key(
        type_="GlobalReference",
        value="mqtt://192.168.0.104:1883/InnoLab/Stoppering",
    ),)
)
cci.submodel_element.endpoints.value.endpoint = {
    "endpoint": Endpoint(value=endpoint_values)
}
skill_values = SkillValues()
skill_values.disabled.value = "false"
cci.submodel_element.skills.value.skill = {"skill": Skill(value=skill_values)}

# ═══════════════════════════════════════════════════════════════════════
# Convert → basyx
# ═══════════════════════════════════════════════════════════════════════
print("=" * 62)
print("  IDTA-Compliant AAS — built from generated templates")
print("=" * 62)

models = {
    "Digital Nameplate (IDTA 02006-3-0)": nameplate,
    "Capability Description (IDTA 02020-1-0)": capability_desc,
    "Control Component Instance (IDTA 02016-2-0)": cci,
}

for label, pydantic_sm in models.items():
    basyx_sm = convert_model_to_submodel(pydantic_sm)
    elements = basyx_sm.submodel_element
    sid = basyx_sm.semantic_id
    sid_val = sid.key[0].value if sid and sid.key else "(none)"

    print(f"\n── {label}")
    print(f"    id_short    = {basyx_sm.id_short!r}")
    print(f"    semantic_id = {sid_val[-60:]}")
    print(f"    elements    = {len(elements)}")

    for el in elements:
        el_sid = getattr(el, "semantic_id", None)
        el_sid_str = ""
        if el_sid and el_sid.key:
            v = el_sid.key[0].value
            el_sid_str = f"  → {v[-55:]}" if len(v) > 55 else f"  → {v}"
        quals = list(getattr(el, "qualifier", None) or [])
        q_tags = "  ".join(f"[{q.type}={q.value}]" for q in quals[:2])
        val = getattr(el, "value", None)
        val_str = ""
        if val is not None:
            try:
                s = str(val)
                val_str = f"  = {s[:40]}" if s else ""
            except Exception:
                val_str = f"  = <{type(val).__name__}>"
        print(f"      {el.id_short!r:30s} {type(el).__name__:20s}{el_sid_str}{val_str}")
        if q_tags:
            print(f"        {'':30s} qualifiers: {q_tags}")

print(f"\n{'=' * 62}")
print("  Key points")
print("  ─────────")
print("  1. Leaf elements are typed: Property, ReferenceElement, File, etc.")
print("  2. Metadata (semantic_id, qualifiers) is on the model, not json_schema_extra.")
print("  3. You set .value on the leaf model — template metadata stays intact.")
print("  4. The converter reads metadata from model instances (not raw dicts).")
print("=" * 62)
