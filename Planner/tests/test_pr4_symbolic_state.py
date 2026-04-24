"""Unit tests for PR4 symbolic-state serialization in the planner.

Covers:
- ``_is_symbolic_fluent`` discrimination.
- Per-action symbolic effect extraction (``_walk_effect_term``).
- Initial-state symbolic-atom collection (via ``build_up_problem``).
- ``bt_to_xml`` emission of ``_planner_initial_state`` on the MainTree
  ``SubTree`` declaration.
- ``resolve_action_execution_ref`` propagation of ``effects``.
"""

from __future__ import annotations

import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from Planner.aas_to_pddl_conversion.up_builder import (  # noqa: E402
    _atom_to_grounded_atom,
    _is_symbolic_fluent,
    _walk_effect_term,
)
from Planner.bt_synthesis.execution_refs import (  # noqa: E402
    resolve_action_execution_ref,
)
from Planner.bt_synthesis.nodes import (  # noqa: E402
    BehaviorTree,
    SuccessLeaf,
)
from Planner.bt_synthesis.xml_writer import bt_to_xml  # noqa: E402


class SymbolicFluentTests(unittest.TestCase):
    def test_no_transformation_is_symbolic(self):
        self.assertTrue(
            _is_symbolic_fluent({"key": "step_done", "transformation_aas_path": ""})
        )
        self.assertTrue(
            _is_symbolic_fluent({"key": "step_done"})  # missing field == empty
        )

    def test_with_transformation_is_not_symbolic(self):
        self.assertFalse(
            _is_symbolic_fluent(
                {
                    "key": "Free",
                    "transformation_aas_path": "Capabilities/Free/Transformation",
                }
            )
        )

    def test_transformation_in_source_binding_is_not_symbolic(self):
        self.assertFalse(
            _is_symbolic_fluent(
                {
                    "key": "Free",
                    "source_bindings": [
                        {"transformation_aas_path": "Capabilities/Free/Transformation"}
                    ],
                }
            )
        )


class WalkEffectTermTests(unittest.TestCase):
    def setUp(self):
        self.fluent_lookup = {
            "step_ready": {"key": "step_ready"},
            "step_done": {"key": "step_done"},
            "Free": {
                "key": "Free",
                "transformation_aas_path": "Capabilities/Free/Transformation",
            },
        }

    def test_atom_pre_grounded_to_object_names(self):
        term = {
            "kind": "atom",
            "fluent": "step_done",
            "params": [
                {"kind": "object", "name": "order_product"},
                {"kind": "object", "name": "step_2"},
            ],
        }
        out: list = []
        _walk_effect_term(term, self.fluent_lookup, out, polarity=True)
        self.assertEqual(
            out, [{"predicate": "step_done", "args": ["order_product", "step_2"], "value": True}]
        )

    def test_not_atom_emits_value_false(self):
        term = {
            "kind": "op",
            "op": "not",
            "children": [
                {
                    "kind": "atom",
                    "fluent": "step_ready",
                    "params": [
                        {"kind": "object", "name": "p"},
                        {"kind": "object", "name": "s"},
                    ],
                }
            ],
        }
        out: list = []
        _walk_effect_term(term, self.fluent_lookup, out, polarity=True)
        self.assertEqual(out, [{"predicate": "step_ready", "args": ["p", "s"], "value": False}])

    def test_and_recurses(self):
        term = {
            "kind": "op",
            "op": "and",
            "children": [
                {
                    "kind": "atom",
                    "fluent": "step_done",
                    "params": [
                        {"kind": "object", "name": "p"},
                        {"kind": "object", "name": "s"},
                    ],
                },
                {
                    "kind": "op",
                    "op": "not",
                    "children": [
                        {
                            "kind": "atom",
                            "fluent": "step_ready",
                            "params": [
                                {"kind": "object", "name": "p"},
                                {"kind": "object", "name": "s"},
                            ],
                        }
                    ],
                },
            ],
        }
        out: list = []
        _walk_effect_term(term, self.fluent_lookup, out, polarity=True)
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0]["predicate"], "step_done")
        self.assertEqual(out[0]["value"], True)
        self.assertEqual(out[1]["predicate"], "step_ready")
        self.assertEqual(out[1]["value"], False)

    def test_sensor_backed_atoms_skipped(self):
        term = {
            "kind": "atom",
            "fluent": "Free",
            "params": [{"kind": "object", "name": "station_1"}],
        }
        out: list = []
        _walk_effect_term(term, self.fluent_lookup, out, polarity=True)
        self.assertEqual(out, [])

    def test_action_param_constant_resolves(self):
        term = {
            "kind": "atom",
            "fluent": "step_done",
            "params": [
                {"kind": "action_param", "index": 0},
                {"kind": "object", "name": "step_2"},
            ],
        }
        out: list = []
        _walk_effect_term(
            term,
            self.fluent_lookup,
            out,
            polarity=True,
            param_remap={0: {"kind": "constant", "object_name": "order_product"}},
        )
        self.assertEqual(out, [{"predicate": "step_done", "args": ["order_product", "step_2"], "value": True}])

    def test_action_param_free_skipped_with_warning(self):
        term = {
            "kind": "atom",
            "fluent": "step_done",
            "params": [
                {"kind": "action_param", "index": 0},
                {"kind": "object", "name": "step_2"},
            ],
        }
        out: list = []
        warnings: list[str] = []
        _walk_effect_term(
            term,
            self.fluent_lookup,
            out,
            polarity=True,
            param_remap={0: {"kind": "free", "up_param": "p0"}},
            warnings=warnings,
            context="action 'X'",
        )
        self.assertEqual(out, [])
        self.assertTrue(any("could not be grounded" in w for w in warnings))


class GroundedAtomHelperTests(unittest.TestCase):
    def test_grounded_atom_value_round_trip(self):
        fluent_lookup = {"p": {"key": "p"}}
        atom = _atom_to_grounded_atom(
            {
                "kind": "atom",
                "fluent": "p",
                "params": [{"kind": "object", "name": "x"}],
            },
            fluent_lookup,
            value=False,
        )
        self.assertEqual(atom, {"predicate": "p", "args": ["x"], "value": False})


class XmlWriterPlannerMetadataTests(unittest.TestCase):
    def test_initial_state_emitted_in_subtree(self):
        bt = BehaviorTree(SuccessLeaf())
        metadata = {
            "initial_state": [
                {"predicate": "step_ready", "args": ["p", "s1"], "value": True},
                {"predicate": "step_done", "args": ["p", "s1"], "value": False},
            ]
        }
        xml = bt_to_xml(bt, planner_metadata=metadata)
        self.assertIn('name="_planner_initial_state"', xml)
        # Encoded JSON is XML-escaped, so look for predicate names.
        self.assertIn("step_ready", xml)
        self.assertIn("step_done", xml)
        # Locate the default attribute and verify the JSON round-trips.
        import re

        m = re.search(
            r'name="_planner_initial_state"\s+default="([^"]+)"', xml
        )
        self.assertIsNotNone(m, "default attribute not found")
        from xml.sax.saxutils import unescape

        decoded = unescape(m.group(1), {"&quot;": '"'})
        atoms = json.loads(decoded)
        self.assertEqual(len(atoms), 2)
        self.assertEqual(atoms[0]["predicate"], "step_ready")
        self.assertEqual(atoms[0]["value"], True)
        self.assertEqual(atoms[1]["value"], False)

    def test_no_initial_state_omits_attribute(self):
        bt = BehaviorTree(SuccessLeaf())
        xml = bt_to_xml(bt)
        self.assertNotIn("_planner_initial_state", xml)

    def test_empty_initial_state_omits_attribute(self):
        bt = BehaviorTree(SuccessLeaf())
        xml = bt_to_xml(bt, planner_metadata={"initial_state": []})
        self.assertNotIn("_planner_initial_state", xml)


class ResolveActionExecutionRefEffectsTests(unittest.TestCase):
    def test_effects_passed_through(self):
        metadata = {
            "action_refs": {
                "act1": {
                    "source_aas_id": "asset",
                    "action_aas_path": "Capabilities/Run",
                    "transformation_aas_path": "",
                    "parameter_bindings": [],
                    "effects": [
                        {"predicate": "step_done", "args": ["p", "s2"], "value": True},
                        {"predicate": "step_ready", "args": ["p", "s2"], "value": False},
                    ],
                }
            },
            "object_refs": {},
        }
        out = resolve_action_execution_ref(metadata, "act1", [])
        self.assertIsNotNone(out)
        self.assertEqual(len(out["effects"]), 2)
        self.assertEqual(out["effects"][0]["predicate"], "step_done")
        self.assertEqual(out["effects"][1]["value"], False)

    def test_missing_effects_field_yields_empty_list(self):
        metadata = {
            "action_refs": {
                "act1": {
                    "source_aas_id": "asset",
                    "action_aas_path": "Capabilities/Run",
                    "transformation_aas_path": "",
                    "parameter_bindings": [],
                }
            },
            "object_refs": {},
        }
        out = resolve_action_execution_ref(metadata, "act1", [])
        self.assertIsNotNone(out)
        self.assertEqual(out["effects"], [])


if __name__ == "__main__":
    unittest.main()
