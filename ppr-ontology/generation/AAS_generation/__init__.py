# `aas_generation.py` was removed; the import is kept guarded so importing this
# package still succeeds for callers that only need its subpackages.
try:
    from .aas_generation import main  # type: ignore[import-not-found]
except ImportError:
    main = None  # type: ignore[assignment]
