from __future__ import annotations

import random
import sys
import unittest
from pathlib import Path


Planner_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = Planner_ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from Planner.bt_synthesis.causal import GroundedAction
from Planner.bt_synthesis.simulator import (
    SimulatedWorld,
    _normalize_outcome_weights,
    build_global_outcome_probability_provider,
)


class SimulatorOutcomeProfilesTests(unittest.TestCase):
    def test_normalize_outcome_weights_rejects_invalid_values(self):
        self.assertIsNone(_normalize_outcome_weights([1.0, -1.0], 2))
        self.assertIsNone(_normalize_outcome_weights([1.0], 2))
        self.assertIsNone(_normalize_outcome_weights([0.0, 0.0], 2))

    def test_strong_skew_profile_prefers_first_outcome(self):
        action = GroundedAction(
            name="flip",
            preconditions=frozenset(),
            neg_preconditions=frozenset(),
            outcomes=[
                (frozenset({"a"}), frozenset({"b"})),
                (frozenset({"b"}), frozenset({"a"})),
            ],
        )
        provider = build_global_outcome_probability_provider("strong_skew")
        world = SimulatedWorld(
            initial_fluents=set(),
            action_table={"flip": action},
            goal_pos=frozenset(),
            goal_neg=frozenset(),
            rng=random.Random(7),
            outcome_probability_provider=provider,
        )

        counts = [0, 0]
        for _ in range(1000):
            world.execute_action("flip")
            assert world.last_outcome_index is not None
            counts[world.last_outcome_index] += 1

        self.assertGreater(counts[0], counts[1])


if __name__ == "__main__":
    unittest.main()
