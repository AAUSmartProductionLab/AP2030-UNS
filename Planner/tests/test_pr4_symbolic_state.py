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

from Planner.step2_pddl_construction.up_builder.bop_encoding import (  # noqa: E402
    _build_effect_branches,
)
from Planner.step2_pddl_construction.up_builder.fluents import (  # noqa: E402
    _atom_to_grounded_atom,
    _is_symbolic_fluent,
    _walk_effect_term,
)
from Planner.step4_policy_to_bt.execution_refs import (  # noqa: E402
    resolve_action_execution_ref,
)
from Planner.step4_policy_to_bt.nodes import (  # noqa: E402
    BehaviorTree,
    SuccessLeaf,
)
from Planner.step6_bt_serialization.xml_writer import bt_to_xml  # noqa: E402


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

    def test_action_param_free_emits_sentinel(self):
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
        # Free action-parameter args are now deferred via a
        # ``$param:N`` sentinel; ``resolve_action_execution_ref``
        # substitutes them at BT-build time.
        self.assertEqual(
            out,
            [
                {
                    "predicate": "step_done",
                    "args": ["$param:0", "step_2"],
                    "value": True,
                }
            ],
        )
        self.assertEqual(warnings, [])

    def test_oneof_picks_success_branch(self):
        # FOND oneOf at the top level of an action's effect list now
        # produces *multiple* branches via _build_effect_branches; the
        # walker itself rejects nested oneOf because there is no
        # carrier for sub-action discriminators.
        term = {
            "kind": "op",
            "op": "oneof",
            "children": [
                {
                    "kind": "atom",
                    "fluent": "step_done",
                    "params": [
                        {"kind": "object", "name": "p"},
                        {"kind": "object", "name": "s"},
                    ],
                }
            ],
        }
        out: list = []
        warnings: list[str] = []
        _walk_effect_term(
            term, self.fluent_lookup, out, polarity=True, warnings=warnings,
            context="action 'X'",
        )
        self.assertEqual(out, [])
        self.assertEqual(len(warnings), 1)
        self.assertIn("oneof", warnings[0].lower())


class BuildEffectBranchesTests(unittest.TestCase):
    def setUp(self):
        self.fluent_lookup = {
            "on": {"key": "on"},
            "productat": {"key": "productat"},
            "step_done": {"key": "step_done"},
            "step_ready": {"key": "step_ready"},
        }

    def _atom(self, name, *args):
        return {
            "kind": "atom",
            "fluent": name,
            "params": [{"kind": "object", "name": a} for a in args],
        }

    def test_no_oneof_emits_single_branch_zero(self):
        terms = [
            self._atom("step_done", "p", "s"),
            {"kind": "op", "op": "not", "children": [self._atom("step_ready", "p", "s")]},
        ]
        out = _build_effect_branches(terms, self.fluent_lookup)
        self.assertEqual(
            out,
            [
                {
                    "branch": 0,
                    "atoms": [
                        {"predicate": "step_done", "args": ["p", "s"], "value": True},
                        {"predicate": "step_ready", "args": ["p", "s"], "value": False},
                    ],
                }
            ],
        )

    def test_oneof_emits_one_branch_per_child(self):
        terms = [
            {
                "kind": "op",
                "op": "oneof",
                "children": [
                    {
                        "kind": "op",
                        "op": "and",
                        "children": [
                            self._atom("on", "p", "t"),
                            self._atom("productat", "p", "loc"),
                        ],
                    },
                    {
                        "kind": "op",
                        "op": "not",
                        "children": [self._atom("on", "p", "t")],
                    },
                ],
            }
        ]
        out = _build_effect_branches(terms, self.fluent_lookup)
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0]["branch"], 0)
        self.assertEqual(out[0]["atoms"][0]["predicate"], "on")
        self.assertEqual(out[0]["atoms"][0]["value"], True)
        self.assertEqual(out[0]["atoms"][1]["predicate"], "productat")
        self.assertEqual(out[1]["branch"], 1)
        self.assertEqual(out[1]["atoms"], [
            {"predicate": "on", "args": ["p", "t"], "value": False},
        ])

    def test_deterministic_atoms_replicated_into_every_branch(self):
        # Captured(p) is deterministic; QualityOk(p) is FOND.
        terms = [
            self._atom("step_done", "p", "s"),
            {
                "kind": "op",
                "op": "oneof",
                "children": [
                    self._atom("on", "p", "t"),
                    {"kind": "op", "op": "not", "children": [self._atom("on", "p", "t")]},
                ],
            },
        ]
        out = _build_effect_branches(terms, self.fluent_lookup)
        self.assertEqual(len(out), 2)
        for branch in out:
            self.assertEqual(branch["atoms"][0]["predicate"], "step_done")
            self.assertEqual(branch["atoms"][0]["value"], True)
        self.assertEqual(out[0]["atoms"][1]["value"], True)
        self.assertEqual(out[1]["atoms"][1]["value"], False)

    def test_empty_effects_emits_single_empty_branch(self):
        out = _build_effect_branches([], self.fluent_lookup)
        self.assertEqual(out, [{"branch": 0, "atoms": []}])


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
                        {
                            "branch": 0,
                            "atoms": [
                                {"predicate": "step_done", "args": ["p", "s2"], "value": True},
                                {"predicate": "step_ready", "args": ["p", "s2"], "value": False},
                            ],
                        }
                    ],
                }
            },
            "object_refs": {},
        }
        out = resolve_action_execution_ref(metadata, "act1", [])
        self.assertIsNotNone(out)
        self.assertEqual(len(out["effects"]), 1)
        self.assertEqual(out["effects"][0]["branch"], 0)
        self.assertEqual(len(out["effects"][0]["atoms"]), 2)
        self.assertEqual(out["effects"][0]["atoms"][0]["predicate"], "step_done")
        self.assertEqual(out["effects"][0]["atoms"][1]["value"], False)

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

    def test_param_sentinels_substituted_with_invocation_args(self):
        metadata = {
            "action_refs": {
                "loading": {
                    "source_aas_id": "asset",
                    "action_aas_path": "Capabilities/Loading",
                    "transformation_aas_path": "",
                    "parameter_bindings": [
                        {
                            "name": "p0",
                            "type": "Resource",
                            "is_constant": True,
                            "bound_object": "imaLoadingSystem",
                            "resolved_kind": "constant",
                            "resolved_up_param": "",
                            "resolved_object": "imaLoadingSystem",
                        },
                        {
                            "name": "p1",
                            "type": "Product",
                            "is_constant": False,
                            "bound_object": "",
                            "resolved_kind": "free",
                            "resolved_up_param": "p0",
                            "resolved_object": "",
                        },
                        {
                            "name": "p2",
                            "type": "Transport",
                            "is_constant": False,
                            "bound_object": "",
                            "resolved_kind": "free",
                            "resolved_up_param": "p1",
                            "resolved_object": "",
                        },
                    ],
                    "effects": [
                        {
                            "branch": 0,
                            "atoms": [
                                {
                                    "predicate": "on",
                                    "args": ["$param:1", "$param:2"],
                                    "value": True,
                                },
                            ],
                        }
                    ],
                }
            },
            "object_refs": {},
        }
        out = resolve_action_execution_ref(
            metadata, "loading", ["mim8_0001", "planarshuttle1"]
        )
        self.assertIsNotNone(out)
        self.assertEqual(
            out["effects"],
            [
                {
                    "branch": 0,
                    "atoms": [
                        {
                            "predicate": "on",
                            "args": ["mim8_0001", "planarshuttle1"],
                            "value": True,
                        }
                    ],
                }
            ],
        )

    def test_param_sentinel_unresolved_drops_atom_keeps_branch(self):
        metadata = {
            "action_refs": {
                "loading": {
                    "source_aas_id": "asset",
                    "action_aas_path": "Capabilities/Loading",
                    "transformation_aas_path": "",
                    "parameter_bindings": [
                        {
                            "name": "p0",
                            "type": "Product",
                            "is_constant": False,
                            "bound_object": "",
                            "resolved_kind": "free",
                            "resolved_up_param": "p0",
                            "resolved_object": "",
                        },
                    ],
                    "effects": [
                        {
                            "branch": 0,
                            "atoms": [
                                {
                                    "predicate": "on",
                                    "args": ["$param:5"],
                                    "value": True,
                                },
                            ],
                        }
                    ],
                }
            },
            "object_refs": {},
        }
        out = resolve_action_execution_ref(metadata, "loading", ["mim8"])
        self.assertIsNotNone(out)
        # Atom dropped (sentinel out of range) but branch preserved so
        # the runtime can still match Outcome=0.
        self.assertEqual(out["effects"], [{"branch": 0, "atoms": []}])

    def test_multi_branch_grounded_independently(self):
        metadata = {
            "action_refs": {
                "loading": {
                    "source_aas_id": "asset",
                    "action_aas_path": "Capabilities/Loading",
                    "transformation_aas_path": "",
                    "parameter_bindings": [
                        {
                            "name": "p0",
                            "type": "Product",
                            "is_constant": False,
                            "bound_object": "",
                            "resolved_kind": "free",
                            "resolved_up_param": "p0",
                            "resolved_object": "",
                        },
                        {
                            "name": "p1",
                            "type": "Transport",
                            "is_constant": False,
                            "bound_object": "",
                            "resolved_kind": "free",
                            "resolved_up_param": "p1",
                            "resolved_object": "",
                        },
                    ],
                    "effects": [
                        {
                            "branch": 0,
                            "atoms": [
                                {"predicate": "on", "args": ["$param:0", "$param:1"], "value": True},
                            ],
                        },
                        {
                            "branch": 1,
                            "atoms": [
                                {"predicate": "on", "args": ["$param:0", "$param:1"], "value": False},
                            ],
                        },
                    ],
                }
            },
            "object_refs": {},
        }
        out = resolve_action_execution_ref(metadata, "loading", ["mim8", "shuttle1"])
        self.assertIsNotNone(out)
        self.assertEqual(len(out["effects"]), 2)
        self.assertEqual(out["effects"][0]["branch"], 0)
        self.assertEqual(out["effects"][0]["atoms"][0]["value"], True)
        self.assertEqual(out["effects"][0]["atoms"][0]["args"], ["mim8", "shuttle1"])
        self.assertEqual(out["effects"][1]["branch"], 1)
        self.assertEqual(out["effects"][1]["atoms"][0]["value"], False)


if __name__ == "__main__":
    unittest.main()
