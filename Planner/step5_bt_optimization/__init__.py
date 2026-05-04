"""Step 5: BT optimization — condition hoisting, parameterization, deduplication."""

from .optimizer import deduplicate_subtrees, optimize_bt, parameterize_subtrees

__all__ = [
    "optimize_bt",
    "deduplicate_subtrees",
    "parameterize_subtrees",
]
