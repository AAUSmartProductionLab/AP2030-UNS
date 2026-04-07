"""
POST /api/guidance/preview

Runs ontology-guided config enrichment on the submitted YAML and returns:
- normalized YAML (with all auto-create/fill guidance applied)
- a list of structured suggestion cards (auto-create, fill, add, hint)
"""
from __future__ import annotations

import copy
import sys
import tempfile
from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from generation.cli.generate_aas import AASGenerator  # noqa: E402
from api.models import GuidanceRequest, GuidanceResponse, GuidanceSuggestion  # noqa: E402

router = APIRouter()


@router.post("/preview", response_model=GuidanceResponse)
async def guidance_preview(req: GuidanceRequest) -> GuidanceResponse:
    try:
        original_config: dict = yaml.safe_load(req.yaml_text)
    except yaml.YAMLError as exc:
        raise HTTPException(status_code=422, detail=f"YAML parse error: {exc}")

    if not isinstance(original_config, dict) or not original_config:
        raise HTTPException(status_code=422, detail="YAML must be a non-empty mapping.")

    # Deep-copy so mutations in _apply_ontology_guidance don't affect the original
    guided_config = copy.deepcopy(original_config)
    system_id = next(iter(guided_config))
    system_config = guided_config[system_id]

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as fh:
        yaml.dump(guided_config, fh, allow_unicode=True)
        tmp_path = fh.name

    try:
        generator = AASGenerator(tmp_path)
        # _apply_ontology_guidance mutates system_config in-place and returns structured suggestions
        raw: list[dict] = generator._apply_ontology_guidance(system_config)
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    suggestions = [
        GuidanceSuggestion(
            field=s["field"],
            action=s["action"],
            description=s["description"],
            preview_value=s.get("proposed_value"),
        )
        for s in raw
    ]

    normalized_yaml = yaml.dump(guided_config, allow_unicode=True, sort_keys=False)
    return GuidanceResponse(normalized_yaml=normalized_yaml, suggestions=suggestions)
