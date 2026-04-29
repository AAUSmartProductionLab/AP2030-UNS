"""
Shared literal normalization utilities for the PR2 BT pipeline.

Provides a single source of truth for parsing, stripping, and splitting
PDDL-style fluent literals used across the BT builder, simulator, causal
analysis, and visualization modules.
"""

from __future__ import annotations

import re
from typing import FrozenSet, List, Optional, Set, Tuple

# ── Predicate parsing ────────────────────────────────────────────────

_PREDICATE_RE = re.compile(r"^(\w+)\((.*)\)$")

# PR2 emits a synthetic ``<none of those>`` literal on partial-state
# conditions to mean "this state is none of the previously listed partial
# states". It is not a real fluent and must never be turned into a
# FluentCheck node or used in state-signature comparisons.
_PLACEHOLDER_LITERALS: frozenset[str] = frozenset({
    "<none of those>",
    "none of those",
    "<none-of-those>",
    "none-of-those",
})


def is_placeholder_literal(literal: object) -> bool:
    """Return ``True`` if *literal* is a PR2 ``<none of those>`` placeholder.

    Handles the optional ``not(...)`` wrapper as well.
    """
    text = str(literal or "").strip().lower()
    if not text:
        return False
    if text.startswith("not(") and text.endswith(")"):
        text = text[4:-1].strip()
    return text in _PLACEHOLDER_LITERALS


def parse_predicate(fluent: str) -> Optional[Tuple[str, List[str]]]:
    """Parse ``name(arg1, arg2, ...)`` into ``(name, [arg1, ...])``.

    Returns ``None`` if *fluent* does not match the expected format.

    >>> parse_predicate("at(shuttle0, loader1)")
    ('at', ['shuttle0', 'loader1'])
    >>> parse_predicate("finished(p0)")
    ('finished', ['p0'])
    >>> parse_predicate("plain_string") is None
    True
    """
    m = _PREDICATE_RE.match(fluent)
    if not m:
        return None
    name = m.group(1)
    args = [a.strip() for a in m.group(2).split(",")]
    return name, args


# ── Negation helpers ─────────────────────────────────────────────────


def strip_negation(literal: str) -> Tuple[str, bool]:
    """Return ``(base_fluent, is_negated)``.

    >>> strip_negation("not(operational(unloader1))")
    ('operational(unloader1)', True)
    >>> strip_negation("operational(shuttle1)")
    ('operational(shuttle1)', False)
    """
    if literal.startswith("not(") and literal.endswith(")"):
        return literal[4:-1], True
    return literal, False


def is_negated(literal: str) -> bool:
    """Return ``True`` if *literal* is wrapped in ``not(...)``."""
    return literal.startswith("not(") and literal.endswith(")")


def normalize_literal(literal: str) -> Tuple[bool, str]:
    """Return ``(is_positive, base_fluent)`` in lowercase.

    Handles both ``not(...)`` and ``!...`` negation styles.

    >>> normalize_literal("NOT(at(s0, l1))")
    (False, 'at(s0, l1)')
    >>> normalize_literal("!up")
    (False, 'up')
    >>> normalize_literal("at(s0, l1)")
    (True, 'at(s0, l1)')
    """
    raw = literal.strip().lower()
    if raw.startswith("not(") and raw.endswith(")"):
        return False, raw[4:-1].strip()
    if raw.startswith("!"):
        return False, raw[1:].strip()
    return True, raw


# ── State splitting ──────────────────────────────────────────────────


def split_state_literals(
    literals: Set[str],
) -> Tuple[FrozenSet[str], FrozenSet[str]]:
    """Split a mixed literal set into positive and negative fluent sets.

    Both sets contain **base fluent names** (without negation wrappers),
    all lowercased.  A fluent appearing in both positive and negative
    forms is resolved to the last occurrence (negative wins over positive
    for the same base).

    >>> sorted(split_state_literals({"at(s0, l1)", "not(operational(d1))"})[0])
    ['at(s0, l1)']
    >>> sorted(split_state_literals({"at(s0, l1)", "not(operational(d1))"})[1])
    ['operational(d1)']
    """
    positive: Set[str] = set()
    negative: Set[str] = set()
    for literal in literals:
        is_pos, base = normalize_literal(literal)
        if not base:
            continue
        if is_pos:
            positive.add(base)
            negative.discard(base)
        else:
            negative.add(base)
            positive.discard(base)
    return frozenset(positive), frozenset(negative)
