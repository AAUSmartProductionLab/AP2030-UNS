"""
POST /api/pipeline/run

Runs guidance → generate → validate in one request.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.models import PipelineRequest, PipelineResponse
from api.routers.guidance import guidance_preview, GuidanceRequest
from api.routers.generate import generate, GenerateRequest
from api.routers.validate import validate_aas, ValidateRequest

router = APIRouter()


@router.post("/run", response_model=PipelineResponse)
async def pipeline_run(req: PipelineRequest) -> PipelineResponse:
    guidance_resp = await guidance_preview(GuidanceRequest(yaml_text=req.yaml_text))
    generate_resp = await generate(GenerateRequest(yaml_text=guidance_resp.normalized_yaml))
    validate_resp = await validate_aas(ValidateRequest(json_text=generate_resp.json_text))
    return PipelineResponse(
        guidance=guidance_resp,
        generate=generate_resp,
        validate=validate_resp,
    )
