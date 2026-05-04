"""Pytest configuration: ensure the local unified-planning checkout is on sys.path.

solver.py already does this at import time, but the ROS 2 launch_testing
pytest plugin collects test modules before normal fixtures run, so
test_pr2_sas_placeholder_expansion.py can fail at collection time if
solver.py hasn't been imported yet. This conftest makes the setup order-
independent.
"""

import sys
from pathlib import Path

_PLANNER_ROOT = Path(__file__).resolve().parent.parent
_UP_ROOT = str(_PLANNER_ROOT / "third_party" / "unified-planning")

if _UP_ROOT not in sys.path:
    sys.path.insert(0, _UP_ROOT)
