from __future__ import annotations

import re
from typing import Any, Optional


def safe_id(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", value or "")
    cleaned = cleaned.strip("_")
    if not cleaned:
        return "id"
    if cleaned[0].isdigit():
        return f"id_{cleaned}"
    return cleaned


def coerce_numeric_literal(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            return None
        try:
            return float(candidate)
        except ValueError:
            return None
    return None


def semantic_tail(value: str) -> str:
    if not value:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    if "#" in text:
        text = text.rsplit("#", 1)[-1]
    text = text.rstrip("/")
    if "/" in text:
        text = text.rsplit("/", 1)[-1]
    # Handle compact CURIE prefixes like "cssx:DispensingCapability"
    if ":" in text and not text.startswith(("http:", "https:", "urn:")):
        text = text.split(":", 1)[-1]
    return text


def normalize_identifier(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]", "", str(value or "").lower())
    return normalized


def capability_name(value: Any) -> str:
    tail = semantic_tail(str(value or ""))
    normalized = normalize_identifier(tail)
    # Strip known suffixes so that e.g. DispensingCapability and DispensingSkill
    # both map to "dispensing" for matching purposes.
    for suffix in ("capability", "skill"):
        if normalized.endswith(suffix) and len(normalized) > len(suffix):
            normalized = normalized[: -len(suffix)]
    return normalized


def match_capability(required_capability: Any, provided_capability: Any) -> bool:
    """Return True when capability identifiers likely refer to the same capability."""
    left = capability_name(required_capability)
    right = capability_name(provided_capability)
    if not left or not right:
        return False
    return left == right
