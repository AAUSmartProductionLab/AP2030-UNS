"""AASBuilderV2 — top-level shell builder.

v1's AASBuilder is namespace/semantic-id-agnostic for the shell construction
itself, so v2 just re-exports it under a new name. Kept as a separate file so
that future shell-level changes (e.g., emitting cssx:representsResource into a
SpecificAssetId) can land here without disturbing v1.
"""
from generation.AAS_generation.core.aas_builder import AASBuilder as AASBuilderV2

__all__ = ["AASBuilderV2"]
