"""
GET /api/generate-context

Returns structured Markdown context for LLM prompt building.
The n8n workflow embeds this text directly into the Claude system prompt.

Query params:
  submodels   Comma-separated SubmodelKey list
              e.g. "Nameplate,HierarchicalStructures,Skills,Capabilities,AID"
  asset_type  Optional string, e.g. "PhysicalResource"
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_CONTEXT_DIR = _PROJECT_ROOT / "api" / "context"

router = APIRouter()

VALID_SUBMODELS: set[str] = {
    "Nameplate",
    "HierarchicalStructures",
    "AID",
    "Skills",
    "Capabilities",
    "Variables",
    "Parameters",
    "AIMC",
}


class ContextResponse(BaseModel):
    context_text: str
    submodels_included: list[str]


@router.get("/generate-context", response_model=ContextResponse)
async def get_generation_context(
    submodels: str = Query(..., description="Comma-separated SubmodelKey list"),
    asset_type: Optional[str] = Query(None, description="Optional asset type hint"),
) -> ContextResponse:
    """Return a single Markdown document suitable for use as an LLM system-prompt context."""
    requested = [s.strip() for s in submodels.split(",") if s.strip() in VALID_SUBMODELS]

    parts: list[str] = []

    # 1. Shared preamble (AAS envelope rules + ID conventions + dependency rules)
    for fname in ("00-preamble.md", "shacl-rules.md"):
        p = _CONTEXT_DIR / fname
        if p.exists():
            parts.append(p.read_text(encoding="utf-8"))

    # 2. Complete valid AAS JSON example
    example = _CONTEXT_DIR / "valid-example.json"
    if example.exists():
        parts.append(
            "## Complete Valid AAS JSON Example\n```json\n"
            + example.read_text(encoding="utf-8")
            + "\n```"
        )

    # 3. Per-submodel template files
    for key in requested:
        sm_file = _CONTEXT_DIR / "submodels" / f"{key.lower()}.md"
        if sm_file.exists():
            parts.append(sm_file.read_text(encoding="utf-8"))

    # 4. Optional asset-type hint
    if asset_type:
        parts.append(f"## Asset Type\nThis AAS describes a `{asset_type}` resource.")

    return ContextResponse(
        context_text="\n\n---\n\n".join(parts),
        submodels_included=requested,
    )
