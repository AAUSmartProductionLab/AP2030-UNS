"""
PDF text and base64 extraction.
- Gemini: reads raw bytes → base64 (sent as inline_data)
- Groq / text mode: extracts Markdown text via pymupdf4llm
"""
from __future__ import annotations

import base64
import time
from pathlib import Path
from typing import Optional
import pymupdf4llm
from .config import Config


def load_pdf(cfg: Config) -> tuple[Optional[str], Optional[str]]:
    """
    Returns (pdf_base64, pdf_text).
    Exactly one will be non-None (depending on provider), or both None if no PDF.
    """
    if cfg.pdf_path is None:
        print("  [SKIP] No PDF configured — text-only mode")
        return None, None

    pdf_path = cfg.pdf_path
    if not pdf_path.exists():
        import sys
        sys.exit(f"ERROR: PDF not found: {pdf_path}")

    if cfg.provider == "gemini":
        pdf_base64 = base64.b64encode(pdf_path.read_bytes()).decode()
        print(f"  [OK] {pdf_path.name}  ({pdf_path.stat().st_size // 1024} KB, sent as inline_data)")
        return pdf_base64, None
    else:
        return None, _extract_text(pdf_path, cfg.max_pdf_chars)


def extract_pdf_text(path: Path, max_chars: Optional[int] = None) -> str:
    """Public helper — extract Markdown text from any PDF file."""
    return _extract_text(path, max_chars)


def _extract_text(pdf_path: Path, max_chars: Optional[int]) -> str:
    print(f"  Extracting text from {pdf_path.name}... ", end="", flush=True)
    t0 = time.time()
    text = pymupdf4llm.to_markdown(str(pdf_path))
    if max_chars and len(text) > max_chars:
        text = text[:max_chars]
        print(f"done in {time.time()-t0:.1f}s  (truncated to {max_chars:,} chars)")
    else:
        print(f"done in {time.time()-t0:.1f}s  ({len(text):,} chars)")
    return text
