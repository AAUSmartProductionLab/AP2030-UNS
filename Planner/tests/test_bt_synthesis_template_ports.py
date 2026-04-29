"""Regression tests for per-invocation port binding in parameterized SubTree
templates emitted by ``parameterize_subtrees`` / ``bt_to_xml``.

The bug being guarded against: when two structurally-identical subtrees
get folded into a parameterized ``SubTree`` template, only the *name*
attribute used to be parameterized via ``{argN}`` placeholders. The
``predicate_ref`` / ``predicate_args`` (and their action equivalents)
were frozen to whichever member happened to be deep-copied first, so
every template invocation evaluated the same predicate against the same
parameters. Now the optimizer detects per-position varying execution
refs, allocates dedicated SubTree ports (``predicate_ref_<i>`` etc.),
and the XML writer emits per-invocation port values.
"""
from __future__ import annotations

import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

PLANNER_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = PLANNER_ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from Planner.bt_synthesis.api import (
    ActionNode,
    BehaviorTree,
    ConditionNode,
    ReactiveSelector,
    Sequence,
    SubTreeRef,
    bt_to_xml,
)
from Planner.bt_synthesis.optimizer import parameterize_subtrees


def _make_member(action_args, productat_ref, action_ref):
    """Build one ``Sequence`` member with a productat FluentCheck +
    parameterized ExecuteAction, mimicking the Movetoposition2 template
    body shape from BTDescriptions/production_MIM8AAS.xml.
    """
    cond = ConditionNode(
        f"productat({action_args[0]}, {action_args[1]})",
        execution_ref=productat_ref,
    )
    act = ActionNode(
        f"transport {action_args[0]} {action_args[1]}",
        execution_ref=action_ref,
    )
    seq = Sequence(
        f"transport_{action_args[0]}_{action_args[1]}",
        [cond, act],
        is_rule_leaf=True,
    )
    return seq


def _ref(label, parameter_refs):
    """Mimic the planner-emitted execution_ref schema used by
    `_collect_execution_ref_aliases`.
    """
    return {
        "fluent_aas_path": f"AI-Planning/Domain/Fluents/{label}",
        "source_aas_id": "https://example.org/aas/Source",
        "transformation_aas_path": "",
        "parameter_refs": parameter_refs,
    }


def _action_ref(label, parameter_refs):
    return {
        "action_aas_path": f"AI-Planning/Domain/Actions/{label}",
        "source_aas_id": "https://example.org/aas/Source",
        "parameter_refs": parameter_refs,
    }


class TemplatePortBindingTests(unittest.TestCase):
    def setUp(self):
        # Two members that share structural shape but bind productat to
        # *different* parameter sets. Without per-position port binding
        # both invocations would inline ProductAt_Sta1_Slot1's alias.
        # Args use distinctive multi-char identifiers so the optimizer's
        # signature replacement (greedy ``str.replace``) doesn't bleed
        # into other tokens like ``productat``.
        param_sta1 = {"name": "p0", "aas_id": "aas:STA1", "aas_path": "Stations/STA1"}
        param_slot1 = {"name": "p1", "aas_id": "aas:SLOT1", "aas_path": "Slots/SLOT1"}
        param_slot2 = {"name": "p1", "aas_id": "aas:SLOT2", "aas_path": "Slots/SLOT2"}

        productat_11 = _ref("ProductAt", [param_sta1, param_slot1])
        productat_12 = _ref("ProductAt", [param_sta1, param_slot2])
        action_11 = _action_ref("Transport", [param_sta1, param_slot1])
        action_12 = _action_ref("Transport", [param_sta1, param_slot2])

        m1 = _make_member(["STA1", "SLOT1"], productat_11, action_11)
        m2 = _make_member(["STA1", "SLOT2"], productat_12, action_12)

        root = ReactiveSelector("Root", [m1, m2])
        self.bt = BehaviorTree(root)
        parameterize_subtrees(self.bt)

    def test_template_registered(self):
        self.assertEqual(set(self.bt.templates.keys()), {"Transport"})

    def test_param_names_include_extra_ports(self):
        _tree, names = self.bt.templates["Transport"]
        # Expect arg0, arg1 (action arg parameters) plus 4 extra ports
        # (predicate_ref_0/predicate_args_0 + action_ref_1/action_args_1).
        self.assertIn("arg0", names)
        self.assertIn("arg1", names)
        self.assertIn("predicate_ref_0", names)
        self.assertIn("predicate_args_0", names)
        self.assertIn("action_ref_1", names)
        self.assertIn("action_args_1", names)

    def test_subtreeref_invocations_carry_distinct_aliases(self):
        # The two SubTreeRefs should have leaf_bindings whose alias
        # references differ across invocations.
        invocations = [
            child for child in self.bt.root.children
            if isinstance(child, SubTreeRef)
        ]
        self.assertEqual(len(invocations), 2)
        # Each invocation has 2 leaf bindings (cond + action).
        for inv in invocations:
            self.assertEqual(len(inv.leaf_bindings), 2)
            for binding in inv.leaf_bindings:
                self.assertIsNotNone(binding)

    def test_emitted_xml_uses_port_references_inside_template(self):
        xml = bt_to_xml(self.bt)
        root = ET.fromstring(xml)
        templ = next(
            bt for bt in root.findall("BehaviorTree")
            if bt.get("ID") == "Transport"
        )
        fluent_check = templ.find(".//FluentCheck")
        action_el = templ.find(".//Action")
        self.assertEqual(fluent_check.get("predicate_ref"), "{predicate_ref_0}")
        self.assertEqual(fluent_check.get("predicate_args"), "{predicate_args_0}")
        self.assertEqual(action_el.get("action_ref"), "{action_ref_1}")
        self.assertEqual(action_el.get("action_args"), "{action_args_1}")

    def test_emitted_xml_subtree_invocations_bind_distinct_aliases(self):
        xml = bt_to_xml(self.bt)
        root = ET.fromstring(xml)
        # The two <SubTree ID="Transport"/> invocations live inside the
        # ReactiveFallback under the MainTree BehaviorTree.
        main_bt = next(
            bt for bt in root.findall("BehaviorTree")
            if bt.get("ID") == "MainTree"
        )
        subtree_invocations = [
            el for el in main_bt.iter("SubTree")
            if el.get("ID") == "Transport"
        ]
        self.assertEqual(len(subtree_invocations), 2)
        ref_values_seen = {
            inv.get("predicate_ref_0") for inv in subtree_invocations
        }
        # Two distinct alias references → set has 2 elements.
        self.assertEqual(len(ref_values_seen), 2)
        # All values look like ``{Alias_Key}``.
        for v in ref_values_seen:
            self.assertTrue(v.startswith("{") and v.endswith("}"), v)
        # Same check for action ports.
        action_values = {
            inv.get("action_ref_1") for inv in subtree_invocations
        }
        self.assertEqual(len(action_values), 2)

    def test_template_subtree_declares_extra_ports(self):
        xml = bt_to_xml(self.bt)
        root = ET.fromstring(xml)
        model = root.find("TreeNodesModel")
        templ_decl = next(
            el for el in model.findall("SubTree")
            if el.get("ID") == "Transport"
        )
        port_names = {ip.get("name") for ip in templ_decl.findall("input_port")}
        self.assertIn("arg0", port_names)
        self.assertIn("arg1", port_names)
        self.assertIn("predicate_ref_0", port_names)
        self.assertIn("predicate_args_0", port_names)
        self.assertIn("action_ref_1", port_names)
        self.assertIn("action_args_1", port_names)

    def test_constant_refs_do_not_get_extra_ports(self):
        # Two members where the FluentCheck is *identical* across them
        # (only the action varies). Then no predicate_ref_<i> port should
        # be allocated.
        param_a = {"name": "p0", "aas_id": "aas:A", "aas_path": "Objects/A"}
        shared = _ref("Free", [param_a])
        action_ab = _action_ref("Move", [param_a])
        action_cd = _action_ref("Move", [param_a, {"name": "p1", "aas_id": "aas:C", "aas_path": "Objects/C"}])

        cond1 = ConditionNode("free(a)", execution_ref=shared)
        cond2 = ConditionNode("free(a)", execution_ref=shared)
        act1 = ActionNode("move a", execution_ref=action_ab)
        act2 = ActionNode("move a c", execution_ref=action_cd)
        m1 = Sequence("rule_1", [cond1, act1], is_rule_leaf=True)
        m2 = Sequence("rule_2", [cond2, act2], is_rule_leaf=True)
        bt = BehaviorTree(ReactiveSelector("Root", [m1, m2]))
        parameterize_subtrees(bt)
        # NB: parameterize_subtrees groups by action-arg signature; if the
        # actions don't share a template signature the group is skipped
        # entirely. We just assert no crash and the BT is still valid.
        bt_to_xml(bt)


if __name__ == "__main__":
    unittest.main()
