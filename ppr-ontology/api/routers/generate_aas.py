"""
POST /api/generate-aas   — SSE streaming AAS generation via generation/ pipeline.
GET  /api/generation-config — available providers and model lists (no API keys).

The endpoint accepts all generation options from the UI. API keys are always
read from generation/config.yaml — they are never exposed to the client.
"""
from __future__ import annotations

import asyncio
import base64
import concurrent.futures
import json
import sys
import tempfile
from pathlib import Path
from typing import AsyncGenerator, Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from generation.config import load_config, Config
from generation.context_loader import load_context
from generation.rag_loader import load_rag
from generation.prompt_builder import build_system_instruction, build_user_prompt
from generation.pipeline import run_pipeline

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class GenerateAasRequest(BaseModel):
    # Asset identity
    asset_name: str = "UnknownAsset"
    base_url: str = "https://smartproductionlab.aau.dk"
    selected_submodels: list[str] = ["Nameplate", "HierarchicalStructures"]

    # Specification input
    spec_sheet_text: str = ""
    spec_sheet_pdf_base64: Optional[str] = None
    spec_sheet_pdf_mime_type: str = "application/pdf"

    # Provider & model selection
    provider: str = "gemini"          # "gemini" | "groq"
    model: Optional[str] = None       # specific model first; falls back to config list

    # Generation options
    generation_mode: str = "json-description"  # "json" | "json-description"
    use_rag: bool = False
    use_example: bool = False
    force_full_aas_output: bool = True
    max_pdf_chars: Optional[int] = 8000
    max_attempts: int = 2


class GenerationConfigResponse(BaseModel):
    providers: list[str]
    models: dict[str, list[str]]
    defaults: dict


# ---------------------------------------------------------------------------
# GET /api/generation-config
# ---------------------------------------------------------------------------

@router.get("/generation-config", response_model=GenerationConfigResponse)
async def get_generation_config() -> GenerationConfigResponse:
    """Return available providers and model lists from config.yaml (no API keys exposed)."""
    try:
        cfg = load_config()
        return GenerationConfigResponse(
            providers=["gemini", "groq"],
            models={
                "gemini": cfg.gemini_models,
                "groq": cfg.groq_models,
            },
            defaults={
                "provider": cfg.provider,
                "generation_mode": "json-description",
                "use_rag": cfg.use_rag,
                "use_example": cfg.use_example,
                "force_full_aas_output": cfg.force_full_aas_output,
                "max_pdf_chars": cfg.max_pdf_chars,
                "max_attempts": cfg.max_attempts,
            },
        )
    except Exception:
        return GenerationConfigResponse(
            providers=["gemini", "groq"],
            models={"gemini": [], "groq": []},
            defaults={},
        )


# ---------------------------------------------------------------------------
# SSE helpers
# ---------------------------------------------------------------------------

def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


# ---------------------------------------------------------------------------
# POST /api/generate-aas  (SSE streaming)
# ---------------------------------------------------------------------------

async def _stream_pipeline(req: GenerateAasRequest) -> AsyncGenerator[str, None]:
    """Run the generation pipeline in a thread and yield SSE events."""

    # -- Load config for API keys and model lists --
    try:
        base_cfg = load_config()
    except SystemExit as exc:
        yield _sse({"type": "error", "message": f"Config load error: {exc}"})
        return
    except Exception as exc:
        yield _sse({"type": "error", "message": f"Config load error: {exc}"})
        return

    # -- Resolve API key --
    api_key = (
        base_cfg.gemini_api_key if req.provider == "gemini" else base_cfg.groq_api_key
    )
    if not api_key:
        yield _sse({
            "type": "error",
            "message": (
                f"No API key configured for provider '{req.provider}' in "
                "generation/config.yaml"
            ),
        })
        return

    # -- Resolve model list (put user-selected model first) --
    base_models = (
        base_cfg.gemini_models if req.provider == "gemini" else base_cfg.groq_models
    )
    if req.model:
        model_list = [req.model, *[m for m in base_models if m != req.model]]
    else:
        model_list = base_models

    # -- Build Config overlay --
    cfg = Config(
        provider=req.provider,
        api_key=api_key,
        asset_name=req.asset_name,
        base_url=req.base_url,
        pdf_path=None,  # PDF arrives via base64 in request body
        submodels=req.selected_submodels,
        generation_mode=req.generation_mode,
        profile_example_path=base_cfg.profile_example_path,
        use_rag=req.use_rag,
        use_example=req.use_example,
        force_full_aas_output=req.force_full_aas_output,
        max_pdf_chars=req.max_pdf_chars,
        max_attempts=req.max_attempts,
        models=model_list,
        gemini_models=base_cfg.gemini_models,
        groq_models=base_cfg.groq_models,
        gemini_api_key=base_cfg.gemini_api_key,
        groq_api_key=base_cfg.groq_api_key,
        gen_dir=base_cfg.gen_dir,
        root_dir=base_cfg.root_dir,
        context_dir=base_cfg.context_dir,
        rag_dir=base_cfg.rag_dir,
        output_json=base_cfg.output_json,
        output_issues=base_cfg.output_issues,
    )

    yield _sse({
        "type": "log",
        "message": (
            f"Starting generation — provider: {req.provider} | "
            f"mode: {req.generation_mode} | "
            f"model: {model_list[0] if model_list else '(default)'} | "
            f"max_attempts: {req.max_attempts}"
        ),
    })

    # -- Set up progress queue so the thread can push events to this coroutine --
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[dict] = asyncio.Queue()

    # Regex patterns used to infer pipeline stage from log text
    import re as _re
    _ATTEMPT_RE = _re.compile(r'--\s+Attempt\s+(\d+)/(\d+)')
    _RESPONSE_RE = _re.compile(r'Response:\s+[\d,]+\s+chars')

    def progress_callback(msg: str) -> None:
        stripped = msg.strip()
        if not stripped:
            return
        # Always emit as a log line
        asyncio.run_coroutine_threadsafe(
            queue.put({"type": "log", "message": stripped}), loop
        )
        # Also emit stage-transition events based on recognisable log patterns
        m = _ATTEMPT_RE.search(stripped)
        if m:
            asyncio.run_coroutine_threadsafe(
                queue.put({
                    "type": "stage",
                    "stage": "querying",
                    "attempt": int(m.group(1)),
                    "max_attempts": int(m.group(2)),
                }),
                loop,
            )
        elif _RESPONSE_RE.search(stripped):
            asyncio.run_coroutine_threadsafe(
                queue.put({
                    "type": "stage",
                    "stage": "validating",
                    "attempt": 0,
                    "max_attempts": cfg.max_attempts,
                }),
                loop,
            )

    # -- Thread worker --
    def _run_in_thread() -> None:
        try:
            # Signal start of preparation stage
            asyncio.run_coroutine_threadsafe(
                queue.put({
                    "type": "stage",
                    "stage": "preparing",
                    "attempt": 0,
                    "max_attempts": cfg.max_attempts,
                }),
                loop,
            )

            # Load context text
            context_text = load_context(cfg)

            # Only load RAG when explicitly requested (can be very large)
            rag_gemini_parts: list[dict] = []
            rag_text_blocks: list[str] = []
            if cfg.use_rag:
                rag_gemini_parts, rag_text_blocks = load_rag(cfg)

            # Build prompts
            system_instruction = build_system_instruction(cfg, context_text, rag_text_blocks)

            # Handle PDF for non-Gemini providers: decode base64 → extract text
            pdf_base64 = req.spec_sheet_pdf_base64
            pdf_text: Optional[str] = None

            if pdf_base64 and req.provider != "gemini":
                try:
                    import pymupdf4llm  # type: ignore
                    pdf_bytes = base64.b64decode(pdf_base64)
                    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
                        f.write(pdf_bytes)
                        tmp_pdf = Path(f.name)
                    text = pymupdf4llm.to_markdown(str(tmp_pdf))
                    tmp_pdf.unlink(missing_ok=True)
                    if req.max_pdf_chars:
                        text = text[: req.max_pdf_chars]
                    pdf_text = text
                    pdf_base64 = None  # Groq uses text, not base64
                except ImportError:
                    # pymupdf4llm not installed — fall through to text-only
                    pdf_base64 = None

            user_prompt = build_user_prompt(cfg, pdf_base64, pdf_text)

            aas_json, conforms, issues, attempts = run_pipeline(
                cfg,
                system_instruction,
                user_prompt,
                pdf_base64,
                rag_gemini_parts,
                progress_callback=progress_callback,
            )

            asyncio.run_coroutine_threadsafe(
                queue.put({
                    "type": "result",
                    "conforms": conforms,
                    "aas_json": aas_json,
                    "attempts": attempts,
                    "issues": issues,
                }),
                loop,
            )
        except BaseException as exc:
            # Catch SystemExit too (llm_client.py calls sys.exit on hard errors)
            asyncio.run_coroutine_threadsafe(
                queue.put({"type": "error", "message": str(exc)}),
                loop,
            )

    # -- Run thread and drain queue as events arrive --
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = loop.run_in_executor(executor, _run_in_thread)

    while True:
        try:
            event = await asyncio.wait_for(queue.get(), timeout=0.3)
            yield _sse(event)
            if event.get("type") in ("result", "error"):
                break
        except asyncio.TimeoutError:
            if future.done():
                # Drain any remaining messages
                while not queue.empty():
                    event = queue.get_nowait()
                    yield _sse(event)
                    if event.get("type") in ("result", "error"):
                        return
                # Thread finished but no result/error event — shouldn't happen
                yield _sse({
                    "type": "error",
                    "message": "Pipeline completed without returning a result.",
                })
                return
        except Exception as exc:
            yield _sse({"type": "error", "message": str(exc)})
            break


@router.post("/generate-aas")
async def generate_aas(req: GenerateAasRequest) -> StreamingResponse:
    return StreamingResponse(
        _stream_pipeline(req),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
