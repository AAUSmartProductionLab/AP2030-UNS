"""
LLM client wrapper around:
- Groq via OpenAI-compatible Python SDK
- Gemini via Google GenAI Python SDK

Keeps the same interface for the generation pipeline, including model-cycling
on rate limits and provider-specific response parsing.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
import json
import sys
import time
from typing import Any
from typing import Optional


REQUEST_TIMEOUT_SECONDS = 90

try:
    from google import genai  # type: ignore[import-not-found]
except Exception:
    genai = None

try:
    from openai import OpenAI  # type: ignore[import-not-found]
except Exception:
    OpenAI = None

def _is_rate_limit_error(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    if status_code == 429:
        return True

    code = getattr(exc, "code", None)
    if code == 429:
        return True

    message = str(exc).lower()
    return "429" in message or "rate limit" in message or "quota" in message


def _is_switchable_model_error(exc: Exception) -> bool:
    if isinstance(exc, TimeoutError):
        return True

    if _is_rate_limit_error(exc):
        return True

    status_code = getattr(exc, "status_code", None)
    code = getattr(exc, "code", None)
    message = str(exc).lower()

    if status_code == 413 or code == 413:
        return True

    token_limit_markers = [
        "request too large",
        "tokens per minute",
        "requested",
        "rate_limit_exceeded",
    ]
    if any(marker in message for marker in token_limit_markers):
        return True

    decommission_markers = [
        "decommissioned",
        "no longer supported",
        "model_decommissioned",
    ]
    if any(marker in message for marker in decommission_markers):
        return True

    return False


def _error_details(exc: Exception) -> tuple[str | None, str | None, str]:
    if isinstance(exc, TimeoutError):
        return None, "timeout", str(exc)

    status_code = getattr(exc, "status_code", None)
    code = getattr(exc, "code", None)

    message_text = str(exc)
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            code = code or err.get("code")
            message_text = str(err.get("message") or message_text)

    return (
        str(status_code) if status_code is not None else None,
        str(code) if code is not None else None,
        message_text,
    )


def _error_category(exc: Exception) -> str:
    if isinstance(exc, TimeoutError):
        return "error"

    message = str(exc).lower()
    if _is_rate_limit_error(exc) or "request too large" in message or "tokens per minute" in message:
        return "limit"
    return "error"


def _invoke_with_timeout(callable_fn, timeout_seconds: int) -> Any:
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(callable_fn)
        try:
            return future.result(timeout=timeout_seconds)
        except FutureTimeoutError as exc:
            raise TimeoutError(f"Request timed out after {timeout_seconds}s") from exc


def _extract_gemini_text(response: Any) -> str:
    text = getattr(response, "text", None)
    if text:
        return str(text)

    try:
        candidates = getattr(response, "candidates", None) or []
        if candidates:
            content = getattr(candidates[0], "content", None)
            parts = getattr(content, "parts", None) or []
            for part in parts:
                part_text = getattr(part, "text", None)
                if part_text:
                    return str(part_text)
    except Exception:
        pass

    return ""


def call_llm(
    provider: str,
    api_key: str,
    models: list[str],
    model_idx: int,
    system_instruction: str,
    gemini_contents: Optional[list[dict]] = None,
    groq_history: Optional[list[dict]] = None,
) -> tuple[str, int]:
    """
    Make one LLM call. Returns (raw_text, model_idx).
    model_idx may change if a 429 caused a model switch.
    Calls sys.exit() if all models are exhausted on 429.
    """
    model_name = models[model_idx]

    if provider == "gemini":
        body_preview = {
            "system_instruction": system_instruction,
            "contents": gemini_contents,
            "generationConfig": {"maxOutputTokens": 32768, "temperature": 0.1},
        }
    else:
        body_preview = {
            "model": model_name,
            "messages": [{"role": "system", "content": system_instruction}] + (groq_history or []),
            "max_tokens": 32768,
            "temperature": 0.1,
        }

    body_kb = len(json.dumps(body_preview, ensure_ascii=False).encode("utf-8")) // 1024
    print(f"  Model: {model_name}  |  Body: {body_kb} KB")
    print("  Calling API... ", end="", flush=True)

    try:
        t0 = time.time()
        if provider == "gemini":
            if genai is None:
                sys.exit("\n[STOP] Missing dependency: google-genai. Install requirements and retry.")

            def _gemini_call() -> str:
                client = genai.Client(api_key=api_key)
                response = client.models.generate_content(
                    model=model_name,
                    contents=gemini_contents or [],
                    config={
                        "system_instruction": system_instruction,
                        "max_output_tokens": 32768,
                        "temperature": 0.1,
                    },
                )
                return _extract_gemini_text(response)

            raw_text = _invoke_with_timeout(_gemini_call, REQUEST_TIMEOUT_SECONDS)
        else:
            if OpenAI is None:
                sys.exit("\n[STOP] Missing dependency: openai. Install requirements and retry.")

            def _groq_call() -> str:
                client = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")
                response = client.chat.completions.create(
                    model=model_name,
                    messages=[{"role": "system", "content": system_instruction}] + (groq_history or []),
                    max_tokens=32768,
                    temperature=0.1,
                )
                return response.choices[0].message.content if response.choices else ""

            raw_text = _invoke_with_timeout(_groq_call, REQUEST_TIMEOUT_SECONDS)

        elapsed = time.time() - t0
        print(f"done in {elapsed:.1f}s")
    except Exception as exc:
        print("failed")
        status_code, code, message_text = _error_details(exc)
        category = _error_category(exc)
        print(
            "  failure details: "
            f"type={category}"
            f", status={status_code or '-'}"
            f", code={code or '-'}"
            f", message={message_text}"
        )
        if _is_switchable_model_error(exc):
            if model_idx < len(models) - 1:
                model_idx += 1
                print(f"  model error/limit — switching to {models[model_idx]}")
                return "", model_idx
            sys.exit(f"\n[STOP] Exhausted all {provider} models due to limits/errors.\n  {exc}")
        sys.exit(f"\n[STOP] Request failed: {exc}")

    return (raw_text or ""), model_idx
