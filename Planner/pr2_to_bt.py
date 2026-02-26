"""
Policy -> reactive Behavior Tree conversion (backward-compatible facade).

This module re-exports the public API that was originally implemented here.
The implementation has been refactored into focused modules:

  - bt_nodes     — BT node types, WorldState, naming helpers
  - bt_builder   — policy_to_bt() and all construction logic
  - bt_optimize  — parameterize / deduplicate passes
  - bt_xml       — BehaviorTree.CPP v4 XML serialization
  - bt_causal    — causal analysis of grounded FOND actions
  - literals     — predicate parsing and literal normalization

Existing imports like ``from pr2_to_bt import policy_to_bt, bt_to_xml``
continue to work unchanged.
"""

from __future__ import annotations

# ── Node types & helpers ──────────────────────────────────────────────
from bt_nodes import (  # noqa: F401
    BTNode,
    BehaviorTree,
    ConditionNode,
    ActionNode,
    ForbiddenActionNode,
    ReactiveSelector,
    ReactiveSequence,
    Inverter,
    SubTreeRef,
    SuccessLeaf,
    FailureLeaf,
    Status,
    WorldState,
    sanitize_bt_id,
    to_camel_case,
    readable_action_id,
)

# ── Core conversion pipeline ─────────────────────────────────────────
from bt_builder import policy_to_bt  # noqa: F401

# ── XML serialization ────────────────────────────────────────────────
from bt_xml import bt_to_xml, count_bt_nodes  # noqa: F401

# ── Optimization passes ──────────────────────────────────────────────
from bt_optimize import (  # noqa: F401
    parameterize_subtrees,
    deduplicate_subtrees,
)

# ── Literal utilities (previously private helpers) ────────────────────
from literals import (  # noqa: F401
    parse_predicate,
    strip_negation,
    is_negated,
    normalize_literal,
    split_state_literals,
)
