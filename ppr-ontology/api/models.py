from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class GuidanceRequest(BaseModel):
    yaml_text: str


class GuidanceSuggestion(BaseModel):
    field: str
    action: str          # "add" | "fill" | "auto-create"
    description: str
    preview_value: Any = None


class GuidanceResponse(BaseModel):
    normalized_yaml: str
    suggestions: list[GuidanceSuggestion]


class GenerateRequest(BaseModel):
    yaml_text: str


class GenerateResponse(BaseModel):
    json_text: str
    messages: list[str]


class ValidateRequest(BaseModel):
    json_text: str


class ValidationIssue(BaseModel):
    severity: str       # "Violation" | "Warning" | "Info"
    message: str
    field: str = ""     # dot-path for UI step routing (e.g. "DigitalNameplate.SerialNumber")
    focus_node: str | None = None
    result_path: str | None = None


class ValidateResponse(BaseModel):
    conforms: bool
    issues: list[ValidationIssue]
    report_ttl: str


class PipelineRequest(BaseModel):
    yaml_text: str


class PipelineResponse(BaseModel):
    guidance: GuidanceResponse
    generate: GenerateResponse
    validate: ValidateResponse
