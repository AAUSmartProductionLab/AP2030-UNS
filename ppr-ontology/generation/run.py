"""
AAS Generation entry point.

Usage (from repo root):
    .venv/Scripts/python -m generation.run
    .venv/Scripts/python -m generation.run --config generation/config.yaml
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from generation.config import load_config
from generation.context_loader import load_context
from generation.AAS_builder import profile_json_text_to_aas_json
from generation.pdf_extractor import load_pdf
from generation.pipeline import run_pipeline
from generation.prompt_builder import build_system_instruction, build_user_prompt
from generation.rag_loader import load_rag


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate AAS JSON from a component spec sheet.")
    parser.add_argument("--config", type=Path, help="Path to config.yaml (default: generation/config.yaml)")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    cfg = load_config(args.config)

    print(f"[OK] Provider: {cfg.provider}  |  Mode: {cfg.generation_mode}  |  API key: {cfg.api_key[:8]}...")

    print("\n[Step 1] Loading context files...")
    context_text = load_context(cfg)

    print(f"\n[Step 2] Loading PDF (provider={cfg.provider})...")
    pdf_base64, pdf_text = load_pdf(cfg)

    rag_gemini_parts: list[dict] = []
    rag_text_blocks: list[str] = []
    if cfg.use_rag:
        print("\n[Step 3] Loading RAG templates...")
        rag_gemini_parts, rag_text_blocks = load_rag(cfg)
    else:
        print("\n[Step 3] Skipping RAG templates (use_rag=false)")

    print("\n[Step 4] Building prompt...")
    system_instruction = build_system_instruction(cfg, context_text, rag_text_blocks)
    user_prompt = build_user_prompt(cfg, pdf_base64, pdf_text)
    print(f"  System instruction: {len(system_instruction):,} chars")
    print(f"  User prompt:        {len(user_prompt):,} chars")

    print(f"\n[Step 5] Generation loop (max {cfg.max_attempts} attempts)...")
    aas_json, conforms, issues, attempts = run_pipeline(
        cfg=cfg,
        system_instruction=system_instruction,
        user_prompt=user_prompt,
        pdf_base64=pdf_base64,
        rag_gemini_parts=rag_gemini_parts,
    )

    print(f"\n[Step 6] Final result — conforms={conforms}, attempts={attempts}")

    cfg.output_json.parent.mkdir(parents=True, exist_ok=True)

    if cfg.generation_mode == "json-description":
        profile_out = cfg.output_json.with_name(cfg.output_json.stem + ".profile.json")
        profile_out.write_text(aas_json, encoding="utf-8")
        print(f"  Profile JSON saved:  {profile_out}")

        if aas_json.strip():
            try:
                full_aas_json, _ = profile_json_text_to_aas_json(aas_json, cfg)
                cfg.output_json.write_text(full_aas_json, encoding="utf-8")
                print(f"  AAS JSON saved:      {cfg.output_json}")
            except Exception as exc:
                print(f"  AAS conversion failed: {exc}")
                cfg.output_json.write_text(aas_json, encoding="utf-8")
                print(f"  Fallback saved:      {cfg.output_json} (raw profile JSON)")
        else:
            cfg.output_json.write_text(aas_json, encoding="utf-8")
            print(f"  AAS JSON saved:      {cfg.output_json}")
    else:
        cfg.output_json.write_text(aas_json, encoding="utf-8")
        print(f"  AAS JSON saved:  {cfg.output_json}")

    if aas_json:
        markers = re.findall(r'\[VERIFY:[^\]]+\]', aas_json)
        if markers:
            print(f"\n  [VERIFY] markers ({len(markers)} total):")
            for marker in markers:
                print(f"    {marker}")

    if issues:
        cfg.output_issues.write_text(json.dumps(issues, indent=2), encoding="utf-8")
        print(f"  Issues file:     {cfg.output_issues}")
        if not conforms:
            print(f"\n  Remaining issues ({len(issues)}):")
            for issue in issues:
                print(f"    [{issue.get('severity','?')}] {issue.get('message','')[:120]}")

    print("\n[Done]")


if __name__ == "__main__":
    main()
