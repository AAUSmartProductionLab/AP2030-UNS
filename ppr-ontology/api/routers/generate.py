"""
POST /api/generate

Accepts generator-profile YAML, runs AASGenerator, returns AAS JSON string.
"""
from __future__ import annotations

import io
import json
import sys
import tempfile
from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from generation.cli.generate_aas import AASGenerator  # noqa: E402
from api.models import GenerateRequest, GenerateResponse  # noqa: E402

router = APIRouter()


@router.post("/generate", response_model=GenerateResponse)
async def generate(req: GenerateRequest) -> GenerateResponse:
    try:
        config: dict = yaml.safe_load(req.yaml_text)
    except yaml.YAMLError as exc:
        raise HTTPException(status_code=422, detail=f"YAML parse error: {exc}")

    if not isinstance(config, dict) or not config:
        raise HTTPException(status_code=422, detail="YAML must be a non-empty mapping.")

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as fh:
        yaml.dump(config, fh, allow_unicode=True)
        tmp_path = fh.name

    messages: list[str] = []

    try:
        # Capture stdout (generator prints guidance messages)
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            generator = AASGenerator(tmp_path)
            system_id = next(iter(config))
            system_config = config[system_id]
            aas_dict = generator.generate_system(system_id, system_config)

        for line in buf.getvalue().splitlines():
            stripped = line.strip().lstrip("•").strip()
            if stripped:
                messages.append(stripped)

    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Generation error: {exc}")
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    json_text = json.dumps(aas_dict, indent=2, ensure_ascii=False)
    return GenerateResponse(json_text=json_text, messages=messages)
