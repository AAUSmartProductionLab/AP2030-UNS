from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import FrozenSet, List, Optional, Tuple


Planner_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = Planner_ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from Planner.step4_policy_to_bt.policy_graph import (  # noqa: E402
    _state_match_score,
    build_policy_state_graph,
)


class _FakeRule:
    def __init__(self, condition_literals: List[str], action_name: str, action_args: Tuple[str, ...] = ()):
        self.raw_condition_literals = list(condition_literals)
        self.action_name = action_name
        self.action_args = action_args


class PolicyGraphTests(unittest.TestCase):
    def test_state_match_accepts_implicit_negative_literals(self):
        score = _state_match_score(
            candidate_positive=frozenset({"at(a)", "done(a)"}),
            candidate_negative=frozenset({"blocked(a)"}),
            simulated_positive=frozenset({"at(a)", "done(a)"}),
            simulated_negative=frozenset(),
        )

        self.assertGreaterEqual(score, 0)

    def test_state_graph_prefers_more_specific_negative_successor(self):
        rules = [
            _FakeRule(["at(a)"], "advance", ("a",)),
            _FakeRule(["at(a)", "done(a)", "not(blocked(a))"], "goal"),
        ]

        def get_action_outcomes(action: str) -> Optional[List[Tuple[FrozenSet[str], FrozenSet[str]]]]:
            if action == "advance(a)":
                return [(frozenset({"done(a)"}), frozenset())]
            return None

        graph = build_policy_state_graph(rules, get_action_outcomes)

        source_signature = frozenset({"at(a)"})
        target_signature = frozenset({"at(a)", "done(a)", "not(blocked(a))"})
        source_id = graph.state_index[source_signature]
        target_id = graph.state_index[target_signature]

        transition = next(
            t
            for t in graph.transitions
            if t.source == source_id and t.action == "advance(a)" and t.outcome == 0
        )

        self.assertEqual(transition.transition_type, "transition")
        self.assertEqual(transition.target, target_id)

    def test_state_graph_ignores_none_of_those_placeholder_literal(self):
        rules = [
            _FakeRule(["ready(a)"], "capture", ("a",)),
            _FakeRule(["done(a)", "qualityok(a)"], "success", ("a",)),
            _FakeRule(["done(a)", "<none of those>"], "fallback", ("a",)),
        ]

        def get_action_outcomes(action: str) -> Optional[List[Tuple[FrozenSet[str], FrozenSet[str]]]]:
            if action == "capture(a)":
                return [
                    (frozenset({"done(a)", "qualityok(a)"}), frozenset({"ready(a)"})),
                    (frozenset({"done(a)"}), frozenset({"ready(a)", "qualityok(a)"})),
                ]
            return None

        graph = build_policy_state_graph(rules, get_action_outcomes)

        source_signature = frozenset({"ready(a)"})
        success_signature = frozenset({"done(a)", "qualityok(a)"})
        fallback_signature = frozenset({"done(a)"})

        source_id = graph.state_index[source_signature]
        success_id = graph.state_index[success_signature]
        fallback_id = graph.state_index[fallback_signature]

        transitions = [
            t
            for t in graph.transitions
            if t.source == source_id and t.action == "capture(a)"
        ]
        by_outcome = {t.outcome: t for t in transitions}

        self.assertEqual(by_outcome[0].transition_type, "transition")
        self.assertEqual(by_outcome[0].target, success_id)
        self.assertEqual(by_outcome[1].transition_type, "transition")
        self.assertEqual(by_outcome[1].target, fallback_id)


if __name__ == "__main__":
    unittest.main()
