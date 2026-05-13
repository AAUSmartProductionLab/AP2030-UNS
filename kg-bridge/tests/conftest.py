"""Pytest configuration for kg-bridge tests."""

import sys
from pathlib import Path

# Add kg-bridge to Python path so that tests can import conversion, etc.
_kg_bridge_dir = Path(__file__).resolve().parent.parent
if str(_kg_bridge_dir) not in sys.path:
    sys.path.insert(0, str(_kg_bridge_dir))
