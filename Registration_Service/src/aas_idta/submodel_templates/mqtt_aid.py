"""
MQTT-extended AssetInterfacesDescription — inherits from generated IDTA AID.

Values-model style: every container holds a dedicated ``{Name}Values`` class
whose fields are the typed child elements (field name == id_short).  Clean
inheritance — subclass the base values class to add/override children instead
of merging string-keyed dicts:

    class MqttFormValues(_BaseFormValues):
        op: Property = Property(...)   # added on top of the base's children

    class MqttForm(_BaseForm):
        value: MqttFormValues = MqttFormValues()

Dynamic name-keyed maps (MQTT actions/properties keyed by action/property
name) stay ``Dict[str, Item]`` — their keys are genuinely dynamic.
"""

from __future__ import annotations

from typing import Dict

from aas_pydantic import (
    ContainerValue, SubmodelElementCollection, Property,
)

from aas_pydantic.submodel_templates.asset_interfaces_description import (
    forms as _BaseForm,
    formsValues as _BaseFormValues,
    property_name as _BaseProperty,
    property_nameValues as _BasePropertyValues,
    actions as _BaseActions,
    properties as _BaseProperties,
    InteractionMetadata as _BaseInteractionMetadata,
    InteractionMetadataValues as _BaseInteractionMetadataValues,
    InterfaceTemplateForMQTT as _BaseMqttInterface,
    InterfaceTemplateForMQTTValues as _BaseMqttInterfaceValues,
    AssetInterfacesDescription as _BaseAID,
    AssetInterfacesDescriptionValues as _BaseAIDValues,
)

from ..constants import (
    AID_MQTT_RESPONSE_FORM, AID_MQTT_RETAIN, AID_MQTT_CONTROL_PACKET,
    AID_MQTT_QOS, AID_INPUT_SCHEMA, AID_OUTPUT_SCHEMA, AID_SYNCHRONOUS,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Delta — MQTT-specific form fields
# ═══════════════════════════════════════════════════════════════════════════════

class MqttResponseFormValues(ContainerValue):
    """MQTT response topic form fields (publish topic for async results)."""
    model_config = {"extra": "forbid"}

    href: Property = Property(
        semantic_id="https://www.w3.org/2019/wot/hypermedia#hasTarget")
    content_type: Property = Property(
        semantic_id="https://www.w3.org/2019/wot/hypermedia#forContentType")
    mqv_retain: Property = Property(
        semantic_id=AID_MQTT_RETAIN)
    mqv_control_packet: Property = Property(
        semantic_id=AID_MQTT_CONTROL_PACKET)


class MqttResponseForm(SubmodelElementCollection):
    """MQTT response topic form (publish topic for async operation results)."""
    semantic_id: str = AID_MQTT_RESPONSE_FORM

    value: MqttResponseFormValues = MqttResponseFormValues()


class MqttFormValues(_BaseFormValues):
    """Standard W3C WoT form + MQTT transport qualifiers."""
    op: Property = Property(
        semantic_id="https://www.w3.org/2019/wot/td#hasOperationType")
    mqv_retain: Property = Property(
        semantic_id=AID_MQTT_RETAIN)
    mqv_qos: Property = Property(
        semantic_id=AID_MQTT_QOS)
    mqv_control_packet: Property = Property(
        semantic_id=AID_MQTT_CONTROL_PACKET)
    response: MqttResponseForm = MqttResponseForm()


class MqttForm(_BaseForm):
    """Standard W3C WoT form + MQTT transport qualifiers."""
    value: MqttFormValues = MqttFormValues()


# ═══════════════════════════════════════════════════════════════════════════════
# Delta — schema URLs on actions / properties
# ═══════════════════════════════════════════════════════════════════════════════

class MqttActionValues(_BasePropertyValues):
    """Standard WoT PropertyDefinition + schema URLs + MQTT form."""
    input_schema: Property = Property(semantic_id=AID_INPUT_SCHEMA)
    output_schema: Property = Property(semantic_id=AID_OUTPUT_SCHEMA)
    synchronous: Property = Property(semantic_id=AID_SYNCHRONOUS)
    forms: MqttForm = MqttForm()


class MqttAction(_BaseProperty):
    """Standard WoT PropertyDefinition + schema URLs + MQTT form."""
    value: MqttActionValues = MqttActionValues()


class MqttPropertyValues(_BasePropertyValues):
    """Standard WoT PropertyDefinition + schema URLs + MQTT form."""
    input_schema: Property = Property(semantic_id=AID_INPUT_SCHEMA)
    output_schema: Property = Property(semantic_id=AID_OUTPUT_SCHEMA)
    forms: MqttForm = MqttForm()


class MqttProperty(_BaseProperty):
    """Standard WoT PropertyDefinition + schema URLs + MQTT form."""
    value: MqttPropertyValues = MqttPropertyValues()


# ═══════════════════════════════════════════════════════════════════════════════
# Delta — action/property containers (dynamic maps: name → Item)
# ═══════════════════════════════════════════════════════════════════════════════

class MqttActions(_BaseActions):
    """Dynamic map of MQTT actions (name → MqttAction)."""
    value: Dict[str, MqttAction] = {}


class MqttProperties(_BaseProperties):
    """Dynamic map of MQTT properties (name → MqttProperty)."""
    value: Dict[str, MqttProperty] = {}


class MqttInteractionMetadataValues(_BaseInteractionMetadataValues):
    """Interaction metadata with MQTT-specialised actions/properties."""
    actions: MqttActions = MqttActions()
    properties: MqttProperties = MqttProperties()


class MqttInteractionMetadata(_BaseInteractionMetadata):
    """Interaction metadata with MQTT-specialised actions/properties."""
    value: MqttInteractionMetadataValues = MqttInteractionMetadataValues()


class MqttInterfaceValues(_BaseMqttInterfaceValues):
    """MQTT interface with extended interaction metadata."""
    interaction_metadata: MqttInteractionMetadata = MqttInteractionMetadata()


class MqttInterface(_BaseMqttInterface):
    """MQTT interface with extended interaction metadata."""
    value: MqttInterfaceValues = MqttInterfaceValues()


# ═══════════════════════════════════════════════════════════════════════════════
# Top-level AID submodel
# ═══════════════════════════════════════════════════════════════════════════════

class MqttAssetInterfacesDescriptionValues(_BaseAIDValues):
    """MQTT-extended AID: interface_mqtt is the MQTT-specialised interface."""
    interface_mqtt: MqttInterface = MqttInterface()


class MqttAssetInterfacesDescription(_BaseAID):
    """MQTT-extended Asset Interfaces Description."""
    submodel_element: MqttAssetInterfacesDescriptionValues = MqttAssetInterfacesDescriptionValues()
