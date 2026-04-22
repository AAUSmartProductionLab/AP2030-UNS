from __future__ import annotations

import sys
import unittest
from pathlib import Path


Planner_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = Planner_ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from Planner.bt_synthesis.api import (
    ActionNode,
    BehaviorTree,
    ConditionNode,
    ReactiveSelector,
    Sequence,
    bt_to_xml,
    count_bt_nodes,
    policy_to_bt,
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
    def __init__(self, policy_result: _FakeResult):
        self.is_solved = True
        self.is_policy = True
        self.is_plan = False
        self.metadata = {}
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


class BTSynthesisHoistingTests(unittest.TestCase):
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
        self.assertEqual(xml.count('fluent="a"'), 1)

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


if __name__ == "__main__":
    unittest.main()
