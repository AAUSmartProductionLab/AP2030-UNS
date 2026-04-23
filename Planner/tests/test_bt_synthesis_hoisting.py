from __future__ import annotations

import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace


Planner_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = Planner_ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from Planner.bt_synthesis.api import (
    ActionNode,
    BehaviorTree,
    ConditionNode,
    ReactiveSelector,
    ReactiveSequence,
    Sequence,
    Status,
    SubTreeRef,
    SuccessLeaf,
    WorldState,
    bt_to_xml,
    count_bt_nodes,
    policy_to_bt,
    policy_to_bt_trivial,
    solve_result_to_bt_xml,
)


class _FakeRule:
    def __init__(self, condition: set[str], action: str):
        self.condition = frozenset(condition)
        self.action = action
        tokens = action.split()
        self.action_name = tokens[0] if tokens else ""
        self.action_args = tuple(tokens[1:])


class _FakeFSAP:
    def __init__(self, condition: set[str], action: str):
        self.condition = frozenset(condition)
        self.action = action
        tokens = action.split()
        self.action_name = tokens[0] if tokens else ""
        self.action_args = tuple(tokens[1:])


class _FakeResult:
    def __init__(self, policy: list[_FakeRule], fsaps: list[_FakeFSAP]):
        self.policy = policy
        self.fsaps = fsaps
        self.domain_pddl = ""
        self.problem_pddl = ""


class _FakeSolveResult:
    def __init__(self, policy_result: _FakeResult, metadata: dict | None = None):
        self.is_solved = True
        self.is_policy = True
        self.is_plan = False
        self.metadata = metadata or {}
        self._policy_result = policy_result

    def require_policy_result(self):
        return self._policy_result


def _naive_rule_tree(policy_rules: list[_FakeRule]) -> BehaviorTree:
    branches = []
    for rule in policy_rules:
        conds = [ConditionNode(c) for c in sorted(rule.condition)]
        branch = Sequence(
            rule.action.replace(" ", "_"),
            conds + [ActionNode(rule.action)],
            is_rule_leaf=True,
        )
        branches.append(branch)

    progression = branches[0] if len(branches) == 1 else ReactiveSelector("Progression", branches)
    return BehaviorTree(ReactiveSelector("PolicyRoot", [progression]))

def _has_linear_condition_sequence_chain(node) -> bool:
    if isinstance(node, Sequence):
        if (
            len(node.children) == 2
            and isinstance(node.children[0], ConditionNode)
            and isinstance(node.children[1], Sequence)
        ):
            return True
        return any(_has_linear_condition_sequence_chain(child) for child in node.children)

    children = getattr(node, "children", None)
    if children is not None:
        return any(_has_linear_condition_sequence_chain(child) for child in children)

    child = getattr(node, "child", None)
    if child is not None:
        return _has_linear_condition_sequence_chain(child)

    return False


class BTSynthesisHoistingTests(unittest.TestCase):
    def test_hoisted_linear_condition_chains_are_flattened(self):
        policy = [
            _FakeRule({"a", "b", "c", "x1"}, "act1 p"),
            _FakeRule({"a", "b", "c", "x2"}, "act2 p"),
            _FakeRule({"a", "b", "c", "x3"}, "act3 p"),
        ]

        bt = policy_to_bt(_FakeResult(policy, []))
        self.assertFalse(_has_linear_condition_sequence_chain(bt.root))

    def test_policy_loop_runs_until_problem_goal_is_satisfied(self):
        policy = [_FakeRule({"ready"}, "act1 p")]
        problem = SimpleNamespace(goals=["done"])

        class _World(WorldState):
            def execute_action(self, action_name: str) -> Status:
                self.fluents.add("done")
                return Status.SUCCESS

        bt = policy_to_bt(_FakeResult(policy, []), problem=problem)
        xml = bt_to_xml(bt)
        world = _World({"ready"})

        self.assertIn("KeepRunningUntilFailure", xml)
        self.assertEqual(bt.tick(world), Status.RUNNING)
        self.assertEqual(bt.tick(world), Status.SUCCESS)
        self.assertTrue(world.goal_reached)

    def test_single_progression_branch_is_not_wrapped_in_policy_root_fallback(self):
        policy = [
            _FakeRule({"a", "b"}, "act1 p"),
            _FakeRule({"a", "c"}, "act2 p"),
        ]

        bt = policy_to_bt(_FakeResult(policy, []))
        xml = bt_to_xml(bt)

        self.assertNotEqual(getattr(bt.root, "name", ""), "PolicyRoot")
        self.assertNotIn('ReactiveFallback name="PolicyRoot"', xml)

    def test_fsaps_do_not_change_generated_bt(self):
        policy = [
            _FakeRule({"a", "b"}, "act1 p"),
            _FakeRule({"a", "c"}, "act2 p"),
        ]

        result_without_fsaps = _FakeResult(policy, [])
        result_with_fsaps = _FakeResult(policy, [_FakeFSAP({"a"}, "act1 p")])

        xml_without = bt_to_xml(policy_to_bt(result_without_fsaps))
        xml_with = bt_to_xml(policy_to_bt(result_with_fsaps))

        self.assertEqual(xml_without, xml_with)
        self.assertNotIn("ForbiddenAction", xml_with)
        self.assertNotIn("FSAP_", xml_with)

    def test_no_done_wrappers_are_emitted(self):
        policy = [
            _FakeRule({"ready"}, "step1"),
            _FakeRule({"not(ready)"}, "step2"),
        ]

        result = _FakeResult(policy, [])
        xml = bt_to_xml(policy_to_bt(result))

        self.assertNotIn("_Done", xml)

    def test_negated_predicate_uses_inverter_decorator(self):
        policy = [_FakeRule({"not(ready(product_1))"}, "dispense product_1")]
        xml = bt_to_xml(policy_to_bt(_FakeResult(policy, [])))

        self.assertIn("<Inverter", xml)
        self.assertIn('Condition ID="FluentCheck" name="ready(product_1)"', xml)
        self.assertNotIn('name="not(ready(product_1))"', xml)

    def test_shared_condition_is_hoisted_once(self):
        policy = [
            _FakeRule({"a", "b"}, "act1 p"),
            _FakeRule({"a", "c"}, "act2 p"),
            _FakeRule({"d"}, "act3 p"),
        ]

        result = _FakeResult(policy, [])
        xml = bt_to_xml(policy_to_bt(result))

        self.assertIn("<Sequence", xml)
        self.assertIn("ReactiveFallback", xml)
        self.assertEqual(xml.count('Condition ID="FluentCheck" name="a"'), 1)

    def test_solve_result_to_bt_xml_ignores_fsaps(self):
        policy = [
            _FakeRule({"a", "b"}, "act1 p"),
            _FakeRule({"a", "c"}, "act2 p"),
        ]
        policy_without_fsaps = _FakeResult(policy, [])
        policy_with_fsaps = _FakeResult(policy, [_FakeFSAP({"a"}, "act1 p")])

        xml_without, warnings_without = solve_result_to_bt_xml(_FakeSolveResult(policy_without_fsaps))
        xml_with, warnings_with = solve_result_to_bt_xml(_FakeSolveResult(policy_with_fsaps))

        self.assertEqual(warnings_without, [])
        self.assertEqual(warnings_with, [])
        self.assertEqual(xml_without, xml_with)
        self.assertNotIn("ForbiddenAction", xml_with)

    def test_solve_result_to_bt_xml_emits_execution_refs(self):
        policy = [_FakeRule({"ready(product_1)"}, "dispense product_1")]
        metadata = {
            "planner_metadata": {
                "action_refs": {
                    "dispense": {
                        "pddl_action_name": "dispense",
                        "source_aas_id": "aas://station/dispense",
                        "source_aas_name": "dispensingStation",
                        "action_aas_path": "AI-Planning/Domain/Actions/Dispense",
                        "transformation_aas_path": "AI-Planning/Domain/Actions/Dispense/Transformation",
                        "transformation": "{\"target\":$states.currentParameter}",
                        "parameter_bindings": [
                            {
                                "name": "product",
                                "type": "Product",
                                "resolved_kind": "free",
                                "resolved_up_param": "p0",
                            }
                        ],
                    }
                },
                "predicate_refs": {
                    "ready": {
                        "fluent_name": "ready",
                        "source_aas_id": "aas://station/dispense",
                        "source_aas_name": "dispensingStation",
                        "fluent_aas_path": "AI-Planning/Domain/Fluents/Ready",
                        "transformation_aas_path": "AI-Planning/Domain/Fluents/Ready/Transformation",
                        "source_bindings": [
                            {
                                "aas_id": "aas://station/dispense",
                                "fluent_aas_path": "AI-Planning/Domain/Fluents/Ready",
                                "transformation_aas_path": "AI-Planning/Domain/Fluents/Ready/Transformation",
                            },
                            {
                                "aas_id": "aas://product/1",
                                "fluent_aas_path": "AI-Planning/Domain/Fluents/Ready",
                                "transformation_aas_path": "AI-Planning/Domain/Fluents/Ready/Transformation",
                            },
                        ],
                        "transformation": "{\"value\":$states.ready}",
                    }
                },
                "object_refs": {
                    "product_1": {
                        "source_aas_id": "aas://product/1",
                        "object_aas_path": "AI-Planning/Problem/Objects/product_1",
                    }
                },
            }
        }

        xml, warnings = solve_result_to_bt_xml(
            _FakeSolveResult(_FakeResult(policy, []), metadata=metadata)
        )

        self.assertEqual(warnings, [])
        self.assertIn("action_ref=", xml)
        self.assertIn("predicate_ref=", xml)
        self.assertIn('<SubTree ID="MainTree" editable="true">', xml)
        self.assertIn('input_port name="Param_product_1"', xml)
        self.assertIn('input_port name="Ready_product_1"', xml)
        self.assertIn('input_port name="Dispense_dispense"', xml)
        self.assertRegex(xml, r'predicate_ref="\{[A-Za-z][A-Za-z0-9_]*\}"')
        self.assertRegex(xml, r'action_ref="\{[A-Za-z][A-Za-z0-9_]*\}"')
        self.assertIn('predicate_args="&quot;{Param_product_1}&quot;"', xml)
        self.assertIn('action_args="&quot;{Param_product_1}&quot;"', xml)
        self.assertIn("&quot;action_aas_path&quot;:&quot;AI-Planning/Domain/Actions/Dispense&quot;", xml)
        self.assertIn("&quot;fluent_aas_path&quot;:&quot;AI-Planning/Domain/Fluents/Ready&quot;", xml)
        self.assertIn("&quot;source_aas_id&quot;:&quot;aas://product/1&quot;", xml)
        self.assertIn("parameter_refs", xml)
        self.assertIn("parameter_link_keys", xml)
        self.assertNotIn("source_aas_name=", xml)
        self.assertNotIn(' action_aas_path="', xml)
        self.assertNotIn(' fluent_aas_path="', xml)
        self.assertNotIn(' source_aas_id="', xml)
        self.assertNotIn(' transformation="', xml)
        self.assertNotIn(' fluent="', xml)
        self.assertNotIn(' action_name="', xml)
        self.assertNotIn('<SetBlackboard', xml)

    def test_execution_ref_args_use_semicolon_delimiter(self):
        condition_ref = {
            "source_aas_id": "aas://station/dispense",
            "fluent_aas_path": "AI-Planning/Domain/Fluents/Ready",
            "parameter_refs": [
                {
                    "aas_id": "aas://product/1",
                    "aas_path": "AI-Planning/Problem/Objects/product_1",
                },
                {
                    "aas_id": "aas://resource/shuttle0",
                    "aas_path": "AI-Planning/Problem/Objects/shuttle0",
                },
            ],
        }
        action_ref = {
            "source_aas_id": "aas://station/dispense",
            "action_aas_path": "AI-Planning/Domain/Actions/Dispense",
            "parameter_refs": [
                {
                    "aas_id": "aas://product/1",
                    "aas_path": "AI-Planning/Problem/Objects/product_1",
                },
                {
                    "aas_id": "aas://resource/shuttle0",
                    "aas_path": "AI-Planning/Problem/Objects/shuttle0",
                },
            ],
        }
        bt = BehaviorTree(
            Sequence(
                "Rule",
                [
                    ConditionNode("ready(product_1)", execution_ref=condition_ref),
                    ActionNode("dispense product_1 shuttle0", execution_ref=action_ref),
                ],
                is_rule_leaf=True,
            )
        )

        xml = bt_to_xml(bt)

        self.assertRegex(xml, r'predicate_args="&quot;\{Param_[A-Za-z0-9_]+\};\{Param_[A-Za-z0-9_]+\}&quot;"')
        self.assertRegex(xml, r'action_args="&quot;\{Param_[A-Za-z0-9_]+\};\{Param_[A-Za-z0-9_]+\}&quot;"')
        self.assertNotIn('predicate_args="&quot;{Param_product_1} {Param_shuttle0}&quot;"', xml)
        self.assertNotIn('action_args="&quot;{Param_product_1} {Param_shuttle0}&quot;"', xml)

    def test_hoisted_subtree_ids_are_compact(self):
        policy = [
            _FakeRule(
                {
                    "not(step_done(order_product, step_5_unloading))",
                    "not(occupied(optimaunloadingsystem, mim8))",
                    "free(planarshuttle3)",
                    "step_ready(order_product, step_1_loading)",
                },
                "act1 p",
            ),
            _FakeRule(
                {
                    "not(step_done(order_product, step_5_unloading))",
                    "not(occupied(optimaunloadingsystem, mim8))",
                    "free(planarshuttle3)",
                    "not(step_done(order_product, step_4_inspection))",
                },
                "act2 p",
            ),
            _FakeRule(
                {
                    "not(step_done(order_product, step_5_unloading))",
                    "not(occupied(optimaunloadingsystem, mim8))",
                    "free(planarshuttle3)",
                    "not(step_done(order_product, step_3_stoppering))",
                },
                "act3 p",
            ),
        ]

        xml = bt_to_xml(policy_to_bt(_FakeResult(policy, [])))
        root = ET.fromstring(xml)
        ids = [el.attrib.get("ID", "") for el in root.findall("BehaviorTree")]

        self.assertTrue(ids)
        self.assertTrue(all(len(identifier) <= 48 for identifier in ids if identifier))
        self.assertTrue(all("_with_" not in identifier and "_else_" not in identifier for identifier in ids))

    def test_template_nodes_use_alias_refs_not_inline_json(self):
        template_tree = Sequence(
            "TemplRule",
            [
                ConditionNode(
                    "ready(product_1)",
                    execution_ref={
                        "source_aas_id": "aas://station/dispense",
                        "fluent_aas_path": "AI-Planning/Domain/Fluents/Ready",
                        "parameter_refs": [
                            {
                                "aas_id": "aas://product/1",
                                "aas_path": "AI-Planning/Problem/Objects/product_1",
                            }
                        ],
                    },
                ),
                ActionNode(
                    "dispense product_1",
                    execution_ref={
                        "source_aas_id": "aas://station/dispense",
                        "action_aas_path": "AI-Planning/Domain/Actions/Dispense",
                        "parameter_refs": [
                            {
                                "aas_id": "aas://product/1",
                                "aas_path": "AI-Planning/Problem/Objects/product_1",
                            }
                        ],
                    },
                ),
            ],
            is_rule_leaf=True,
        )

        bt = BehaviorTree(Sequence("Root", [SubTreeRef("TemplAction", {"arg0": "product_1"}), SuccessLeaf()]))
        bt.templates = {"TemplAction": (template_tree, ["arg0"])}

        xml = bt_to_xml(bt)

        self.assertIn('BehaviorTree ID="TemplAction"', xml)
        self.assertRegex(xml, r'predicate_ref="\{[A-Za-z][A-Za-z0-9_]*\}"')
        self.assertRegex(xml, r'action_ref="\{[A-Za-z][A-Za-z0-9_]*\}"')
        self.assertNotIn('predicate_ref="{&quot;', xml)
        self.assertNotIn('action_ref="{&quot;', xml)

    def test_reactive_fallback_names_are_compact(self):
        policy = [
            _FakeRule(
                {
                    "not(step_done(order_product, step_5_unloading))",
                    "not(occupied(optimaunloadingsystem, mim8))",
                    "free(planarshuttle3)",
                    "step_ready(order_product, step_1_loading)",
                },
                "act1 p",
            ),
            _FakeRule(
                {
                    "not(step_done(order_product, step_5_unloading))",
                    "not(occupied(optimaunloadingsystem, mim8))",
                    "free(planarshuttle3)",
                    "not(step_done(order_product, step_4_inspection))",
                },
                "act2 p",
            ),
            _FakeRule(
                {
                    "not(step_done(order_product, step_5_unloading))",
                    "not(occupied(optimaunloadingsystem, mim8))",
                    "free(planarshuttle3)",
                    "not(step_done(order_product, step_3_stoppering))",
                },
                "act3 p",
            ),
        ]

        xml = bt_to_xml(policy_to_bt(_FakeResult(policy, [])))
        root = ET.fromstring(xml)
        fallback_names = [
            el.attrib.get("name", "")
            for el in root.findall(".//ReactiveFallback")
        ]

        self.assertTrue(fallback_names)
        self.assertTrue(all(len(name) <= 64 for name in fallback_names if name))
        self.assertTrue(all("_with_" not in name and "_else_" not in name for name in fallback_names))

    def test_hoisting_reduces_node_count_vs_naive_selector(self):
        policy = [
            _FakeRule({"a", "shared1", "shared2", "x1"}, "act1 p"),
            _FakeRule({"a", "shared1", "shared2", "x2"}, "act2 p"),
            _FakeRule({"a", "shared1", "shared2", "x3"}, "act3 p"),
            _FakeRule({"a", "shared1", "shared2", "x4"}, "act4 p"),
        ]

        optimized_bt = policy_to_bt(_FakeResult(policy, []))
        naive_bt = _naive_rule_tree(policy)

        optimized_count = count_bt_nodes(optimized_bt.root)
        naive_count = count_bt_nodes(naive_bt.root)

        self.assertLess(optimized_count, naive_count)

    def test_trivial_mode_keeps_shared_conditions_unhoisted(self):
        policy = [
            _FakeRule({"a", "b"}, "act1 p"),
            _FakeRule({"a", "c"}, "act2 p"),
        ]

        hoisted_xml = bt_to_xml(policy_to_bt(_FakeResult(policy, [])))
        trivial_xml = bt_to_xml(policy_to_bt_trivial(_FakeResult(policy, [])))

        self.assertEqual(hoisted_xml.count('Condition ID="FluentCheck" name="a"'), 1)
        self.assertGreaterEqual(
            trivial_xml.count('Condition ID="FluentCheck" name="a"'),
            2,
        )

    def test_hoisted_vs_trivial_preserve_tick_outcome(self):
        policy = [
            _FakeRule({"a", "b"}, "act1 p"),
            _FakeRule({"a", "c"}, "act2 p"),
        ]

        class _World(WorldState):
            def __init__(self):
                super().__init__({"a", "b"})

            def execute_action(self, action_name: str) -> Status:
                self.goal_reached = True
                return Status.SUCCESS

        hoisted_bt = policy_to_bt(_FakeResult(policy, []))
        trivial_bt = policy_to_bt_trivial(_FakeResult(policy, []))

        self.assertEqual(hoisted_bt.tick(_World()), Status.SUCCESS)
        self.assertEqual(trivial_bt.tick(_World()), Status.SUCCESS)


if __name__ == "__main__":
    unittest.main()
