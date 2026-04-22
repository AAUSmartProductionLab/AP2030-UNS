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

Existing imports like ``from bt_synthesis.api import policy_to_bt, bt_to_xml``
continue to work unchanged.
"""

from __future__ import annotations

# ── Node types & helpers ──────────────────────────────────────────────
from .nodes import (  # noqa: F401
    BTNode,
    BehaviorTree,
    ConditionNode,
    ActionNode,
    ForbiddenActionNode,
    Sequence,
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
from .builder import policy_to_bt  # noqa: F401

# ── XML serialization ────────────────────────────────────────────────
from .xml_writer import bt_to_xml, count_bt_nodes  # noqa: F401

# ── Optimization passes ──────────────────────────────────────────────
from .optimizer import (  # noqa: F401
    parameterize_subtrees,
    deduplicate_subtrees,
)

# ── BT artifact utilities ───────────────────────────────────────────
from .artifacts import generate_bt_filename, save_bt_xml  # noqa: F401

# ── Solve-result and deterministic plan conversion ───────────────────
from .plan_converters import (  # noqa: F401
    action_instance_to_bt_action,
    deterministic_plan_to_bt_xml,
    extract_plan_text,
    format_action_instance,
    solve_result_to_bt_xml,
)

# ── Literal utilities (previously private helpers) ────────────────────
from .literals import (  # noqa: F401
    parse_predicate,
    strip_negation,
    is_negated,
    normalize_literal,
    split_state_literals,
)
