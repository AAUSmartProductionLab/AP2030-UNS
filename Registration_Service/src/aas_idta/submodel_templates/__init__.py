"""
Custom aas_pydantic submodel templates — project-specific and IDTA-extended models.

These models follow the same pattern as aas_pydantic generated templates:
- Submodel/SubmodelElementCollection base classes
- Inline semantic_id, description, qualifiers on every class and leaf element
- Typed leaf elements (Property, ReferenceElement, File, etc.) with defaults

Modules:
    mqtt_aid           — MQTT-extended AssetInterfacesDescription
    execution_model    — Skills ExecutionModel (parameters, conditions, effects)
    skills             — Extended CCI Skill with ExecutionModel
    variables          — Variables submodel (custom, not yet IDTA)
    parameters         — Parameters submodel (custom, not yet IDTA)
"""

from .mqtt_aid import (
    MqttAssetInterfacesDescription,
    MqttAction,
    MqttProperty,
    MqttForm,
    MqttResponseForm,
)
from .control_component_instance import (
    ExecutionModel,
    ExecutionModelParameter,
    PredicateCondition,
    ExtendedSkill,
    ExtendedSkills,
)
from .variables import Variables
from .parameters import Parameters

__all__ = [
    # MQTT AID
    "MqttAssetInterfacesDescription",
    "MqttAction",
    "MqttProperty",
    "MqttForm",
    "MqttResponseForm",
    # Execution model
    "ExecutionModel",
    "ExecutionModelParameter",
    "PredicateCondition",
    # Skills
    "ExtendedSkill",
    # Custom submodels
    "Variables",
    "Parameters",
]
