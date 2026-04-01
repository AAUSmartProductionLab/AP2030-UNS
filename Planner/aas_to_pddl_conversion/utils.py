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
