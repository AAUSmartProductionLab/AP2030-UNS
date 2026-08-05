"""Resource AAS — Pydantic model for a Resource AAS with type-level defaults.

All Resources must implement certain skills (Halt, Occupy, Release), expose
a StationState property, track PackMLState, and declare a Location.  These
defaults are baked into the Pydantic model so individual station configs
only need to specify the delta.

Station configs override fields via model_validate() — missing fields
fall back to these defaults.

Container-style: children live in ``value`` / ``submodel_element`` dicts
keyed by id_short (basyx/IDTA-aligned).
"""

from __future__ import annotations

from typing import Dict, Optional

from pydantic import BaseModel

from aas_pydantic import (
    AAS, ExternalReference, Key, ModelReference, Property,
    ReferenceElement, SubmodelElement,
)

from aas_pydantic.submodel_templates.nameplate import Nameplate
from aas_pydantic.submodel_templates.capability_description import CapabilityDescription
from aas_pydantic.submodel_templates.control_component_instance import (
    ControlComponentInstance, Endpoints, Endpoint,
)
from aas_pydantic.submodel_templates.hierarchical_structures import HierarchicalStructures
from aas_pydantic.submodel_templates.asset_interfaces_description import EndpointMetadata
from aas_pydantic.submodel_templates.asset_interfaces_description import (
    InterfaceTemplateForMQTT as _BaseMqttInterface,
    securityDefinitions as SecurityDefinitions,
)

from ..submodel_templates.mqtt_aid import (
    MqttAssetInterfacesDescription, MqttInterface, MqttInteractionMetadata,
    MqttActions, MqttProperties, MqttAction, MqttProperty,
    MqttForm, MqttResponseForm,
)
from ..submodel_templates.variables import (
    Variables, VariableItem, VariableInterfaceReference,
)
from ..submodel_templates.parameters import (
    Parameters, ParameterItem,
)
from .parameters import Position, ResourceParameters
from ..submodel_templates.control_component_instance import (
    ExtendedSkill, ExtendedSkills,
)

from ..constants import (
    BASE_URL, SCHEMA_BASE, BROKER, SITE,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Shared submodel factory helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _put(container, key: str, element: SubmodelElement) -> SubmodelElement:
    """Assign *element* into *container* under *key*, stamping its id_short
    from the key.

    *container* is a values model (``setattr`` onto an existing field) or a
    dynamic ``Dict[str, X]`` map (``container[key] = ...``).  The key is the
    single source of truth for the id_short."""
    element.id_short = key
    if isinstance(container, BaseModel):
        setattr(container, key, element)
    else:
        container[key] = element
    return element


def _mqtt_action(name: str, *, synchronous: bool = False, has_response: bool = True) -> MqttAction:
    """Build a standard MQTT action with default form settings."""
    action = MqttAction()
    action.value.key.value = name
    action.value.title.value = name
    action.value.synchronous.value = str(synchronous).lower()
    action.value.input_schema.value = f"{SCHEMA_BASE}/command.schema.json"
    action.value.output_schema.value = (
        f"{SCHEMA_BASE}/commandResponse.schema.json" if has_response else ""
    )
    forms = action.value.forms
    forms.value.href.value = f"/CMD/{name}"
    forms.value.op.value = "invokeAction"
    forms.value.mqv_retain.value = "false"
    forms.value.mqv_control_packet.value = "subscribe"
    forms.value.mqv_qos.value = "2"
    if has_response:
        _put(
            forms.value, "response",
            MqttResponseForm(
                value={
                    "href": Property(value=f"/DATA/{name}"),
                    "content_type": Property(value="application/json"),
                    "mqv_control_packet": Property(value="publish"),
                    "mqv_retain": Property(value="false"),
                },
            ),
        )
    return action


def _mqtt_property(name: str, href: str, *, retain: bool = True, qos: int = 0) -> MqttProperty:
    """Build a standard MQTT property with default form settings."""
    prop = MqttProperty()
    prop.value.key.value = name
    prop.value.title.value = name
    prop.value.output_schema.value = f"{SCHEMA_BASE}/stationState.schema.json"
    forms = prop.value.forms
    forms.value.href.value = href
    forms.value.mqv_retain.value = str(retain).lower()
    forms.value.mqv_control_packet.value = "publish"
    forms.value.mqv_qos.value = str(qos)
    return prop


def _extended_skill(name: str, *, aas_id: str = "", disabled: bool = False) -> ExtendedSkill:
    """Build a standard ExtendedSkill for the CCI."""
    skill = ExtendedSkill()
    skill.value.disabled.value = str(disabled).lower()
    if aas_id:
        _put(
            skill.value, "interface_reference",
            ReferenceElement(
                value=ModelReference(key=(Key(type_="AssetAdministrationShell", value=aas_id),))
            ),
        )
    return skill


def _variable(sem_uri: str, iface_name: str, field: str) -> VariableItem:
    """Build a VariableItem, preserving the values-model semantic_id defaults."""
    v = VariableItem()
    v.value.semantic_id_param.value = sem_uri
    ref = v.value.interface_reference
    ref.value.name.value = iface_name
    ref.value.field.value = field
    return v


def _nameplate() -> Nameplate:
    """Nameplate with station-agnostic defaults (rest comes from the template)."""
    np = Nameplate(id_short="Nameplate")
    np.submodel_element.year_of_construction.value = "2026"
    np.submodel_element.country_of_origin.value = "DK"
    return np


def _aid() -> MqttAssetInterfacesDescription:
    """AssetInterfacesDescription with mandatory Resource actions/properties."""
    aid = MqttAssetInterfacesDescription(id_short="AssetInterfacesDescription")
    iface = aid.submodel_element.interface_mqtt
    ep = iface.value.endpoint_metadata
    ep.value.base.value = f"{BROKER}/{SITE}/{{station_name}}"
    ep.value.content_type.value = "application/json"
    im = iface.value.interaction_metadata
    actions = im.value.actions
    _put(actions.value, "Halt", _mqtt_action("Halt", synchronous=True, has_response=False))
    _put(actions.value, "Occupy", _mqtt_action("Occupy", synchronous=True))
    _put(actions.value, "Release", _mqtt_action("Release", synchronous=True))
    props = im.value.properties
    _put(props.value, "StationState", _mqtt_property("StationState", "/DATA/State"))
    return aid


def _cci() -> "ResourceControlComponentInstance":
    """ControlComponentInstance with mandatory Resource skills + MQTT endpoint."""
    cci = ResourceControlComponentInstance(id_short="ControlComponentInstance")
    _put(
        cci.submodel_element, "endpoints",
        Endpoints(
            value={
                # ``endpoint`` is a multi-cardinality map (name → Endpoint)
                "endpoint": {
                    "endpoint": Endpoint(
                        value={
                            "interface_reference": ReferenceElement(
                                value=ExternalReference(key=(Key(type_="GlobalReference", value="https://admin-shell.io/idta/ControlComponent/Interface/MQTT/1/0"),))
                            ),
                            "endpoint_reference": ReferenceElement(
                                value=ExternalReference(key=(Key(type_="GlobalReference", value=f"{BROKER}/{SITE}/{{station_name}}"),))
                            ),
                        },
                    ),
                },
            },
        ),
    )
    skills = ExtendedSkills()
    _put(skills.value, "Halt", _extended_skill("Halt"))
    _put(skills.value, "Occupy", _extended_skill("Occupy"))
    _put(skills.value, "Release", _extended_skill("Release"))
    _put(cci.submodel_element, "skills", skills)
    _put(cci.submodel_element, "type", ReferenceElement())
    return cci


# ═══════════════════════════════════════════════════════════════════════════════
# Submodel field names — documented for reference (model walking replaces old injection)
# ═══════════════════════════════════════════════════════════════════════════════

SUBMODEL_FIELDS = (
    "nameplate", "asset_interfaces_description", "control_component_instance",
    "capability_description", "hierarchical_structures", "variables", "parameters",
)


# ═══════════════════════════════════════════════════════════════════════════════
# ResourceTypeAAS — the type model with defaults
# ═══════════════════════════════════════════════════════════════════════════════

class ResourceControlComponentInstance(ControlComponentInstance):
    """CCI variant that uses ExtendedSkills in the ``submodel_element`` container."""


class ResourceTypeAAS(AAS):
    """Resource AAS type — all Resources share these defaults.

    Individual stations override via JSON config.  Fields not specified
    in the station config fall back to the defaults below.

    Mandatory for all resources:
        - Halt, Occupy, Release actions (MQTT + CCI skills)
        - StationState property
        - PackMLState and OccupationState variables
        - Location parameter
    """

    model_config = {"extra": "forbid"}

    # ── Nameplate ─────────────────────────────────────────────────────────
    nameplate: Nameplate = _nameplate()

    # ── Asset Interfaces Description ──────────────────────────────────────
    asset_interfaces_description: MqttAssetInterfacesDescription = _aid()

    # ── Control Component Instance ────────────────────────────────────────
    control_component_instance: ResourceControlComponentInstance = _cci()

    # ── Variables ─────────────────────────────────────────────────────────
    variables: Variables = Variables(
        id_short="Variables",
        submodel_element={
            "PackMLState": _variable(
                "https://w3id.org/2026/apex/semantic/state/operational",
                "StationState", "State",
            ),
            "OccupationState": _variable(
                "https://w3id.org/2026/apex/semantic/state/occupied",
                "StationState", "ProcessQueue",
            ),
        },
    )

    parameters: ResourceParameters = ResourceParameters(id_short="Parameters")

    # ── Optional submodels (no defaults — stations opt in) ────────────────
    capability_description: Optional[CapabilityDescription] = None
    hierarchical_structures: Optional[HierarchicalStructures] = None
