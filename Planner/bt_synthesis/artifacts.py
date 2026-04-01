from __future__ import annotations

import os
from typing import Any, Mapping


def generate_bt_filename(product_config: Mapping[str, Any]) -> str:
    """Generate a deterministic BT filename from product metadata."""
    product_id = str(product_config.get("id", "") or "")
    if product_id:
        product_name = product_id.rstrip("/").split("/")[-1]
    else:
        product_name = str(product_config.get("idShort", "unknown") or "unknown")
    clean_name = "".join(c for c in product_name if c.isalnum() or c in "-_")
    return f"production_{clean_name}.xml"


def save_bt_xml(bt_xml: str, path: str) -> None:
    """Persist behavior tree XML to disk, creating parent directory if needed."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as file_handle:
        file_handle.write(bt_xml)
