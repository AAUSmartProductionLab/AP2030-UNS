"""Unit tests for the AI Planning action transition builder.

Verifies that ``_PlanningTransitionBuilder.build_transition_item`` emits
the new ``Transformation`` String Property and ``Constants`` SMC siblings
when the YAML action specifies them, and that those elements are
omitted otherwise.

The runtime contract these tests pin down:

* ``Transformation`` is a String Property holding a JSONata expression
  consumed by ``ExecuteAction`` to build the published MQTT message.
* ``Constants`` is a Submodel Element Collection holding per-action
  constant values referenced by the JSONata expression as
  ``constants.<name>``.
* Both are siblings of ``Parameters`` / ``Conditions`` / ``Effects``
  inside the action's SMC, mirroring the layout used by ``Fluent`` items.
"""

from __future__ import annotations

import os
import sys
from typing import Any, Optional

import pytest
from basyx.aas import model

# Allow ``from src...`` imports the same way the integration script does.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.aas_generation.submodels.ai_planning_components import (  # noqa: E402
    _PlanningBuildContext,
    _PlanningReferenceBuilder,
    _PlanningTermBuilder,
    _PlanningTransitionBuilder,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_string_property(id_short: str, value: str) -> model.Property:
    return model.Property(
        id_short=id_short,
        value_type=model.datatypes.String,
        value=value,
    )


def _make_constants_smc(constants: Any) -> Optional[model.SubmodelElementCollection]:
    if not isinstance(constants, dict) or not constants:
        return None
    properties = [
        model.Property(
            id_short=str(name),
            value_type=model.datatypes.String,
            value=str(val),
        )
        for name, val in constants.items()
    ]
    return model.SubmodelElementCollection(id_short="Constants", value=properties)


def _make_typed_property(id_short: str, value: Any, _type_hint: Optional[str]) -> model.Property:
    return model.Property(
        id_short=id_short,
        value_type=model.datatypes.String,
        value=str(value),
    )


def _make_builder() -> _PlanningTransitionBuilder:
    base_url = "http://example.org"
    context = _PlanningBuildContext()
    references = _PlanningReferenceBuilder(base_url=base_url, context=context)
    terms = _PlanningTermBuilder(references=references, typed_property_factory=_make_typed_property)

    def _build_action_parameters(_system_id, _action_key, _parameters):
        # Minimal stand-in; tests don't assert on Parameters layout.
        return None

    return _PlanningTransitionBuilder(
        base_url=base_url,
        context=context,
        terms=terms,
        build_action_parameters=_build_action_parameters,
        string_property_factory=_make_string_property,
        constants_factory=_make_constants_smc,
    )


def _children(smc: model.SubmodelElementCollection) -> dict:
    return {child.id_short: child for child in smc.value}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_action_emits_transformation_property_when_specified():
    builder = _make_builder()

    action_smc = builder.build_transition_item(
        system_id="imaDispensingSystemAAS",
        section_name="Actions",
        key="Dispense",
        parameters=[],
        conditions={},
        effects={},
        item_semantic_id="https://example.org/semantic/Action",
        skill_reference="Dispense",
        transformation='{"Uuid": params[1].Parameters.Uuid}',
        constants=None,
    )

    children = _children(action_smc)
    assert "Transformation" in children, (
        "Action SMC must include a Transformation Property when YAML provides one"
    )
    transformation = children["Transformation"]
    assert isinstance(transformation, model.Property)
    assert transformation.value == '{"Uuid": params[1].Parameters.Uuid}'


def test_action_emits_constants_smc_when_specified():
    builder = _make_builder()

    action_smc = builder.build_transition_item(
        system_id="imaDispensingSystemAAS",
        section_name="Actions",
        key="Dispense",
        parameters=[],
        conditions={},
        effects={},
        item_semantic_id="https://example.org/semantic/Action",
        skill_reference="Dispense",
        transformation=None,
        constants={"speed": 42, "mode": "fast"},
    )

    children = _children(action_smc)
    assert "Constants" in children
    constants_smc = children["Constants"]
    assert isinstance(constants_smc, model.SubmodelElementCollection)
    constant_children = _children(constants_smc)
    assert set(constant_children.keys()) == {"speed", "mode"}


def test_action_omits_transformation_and_constants_when_absent():
    builder = _make_builder()

    action_smc = builder.build_transition_item(
        system_id="imaDispensingSystemAAS",
        section_name="Actions",
        key="Idle",
        parameters=[],
        conditions={},
        effects={},
        item_semantic_id="https://example.org/semantic/Action",
        skill_reference="Idle",
        transformation=None,
        constants=None,
    )

    children = _children(action_smc)
    assert "Transformation" not in children
    assert "Constants" not in children


def test_build_transition_section_propagates_transformation_from_yaml():
    """End-to-end: a YAML action item dict goes through build_transition_section
    and the resulting Action SMC carries the Transformation property.
    """
    builder = _make_builder()

    actions_cfg = [
        {
            "key": "Dispense",
            "parameters": [],
            "SkillReference": "Dispense",
            "transformation": '{"Uuid": params[1].Parameters.Uuid, "TargetMass": params[1].Parameters.TargetMass}',
            "constants": {"timeout_ms": 5000},
            "conditions": {},
            "effects": {},
        }
    ]

    section = builder.build_actions_section(
        system_id="imaDispensingSystemAAS",
        actions_cfg=actions_cfg,
    )

    assert section.id_short == "Actions"
    actions_by_key = _children(section)
    assert "Dispense" in actions_by_key

    action_children = _children(actions_by_key["Dispense"])
    assert "Transformation" in action_children
    assert action_children["Transformation"].value.startswith('{"Uuid": params[1]')
    assert "Constants" in action_children
    constants_children = _children(action_children["Constants"])
    assert "timeout_ms" in constants_children


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
