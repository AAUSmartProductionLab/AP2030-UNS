"""CLI entry point for the AAS generation pipeline.

Usage:
    python run_pipeline.py [--config path/to/config.yaml]

Reads generation/config.yaml (or the path given via --config), runs the
full generation + validation loop, and writes the AAS JSON and issues list
to the paths configured under output.json_file / output.issues_file.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from generation.config import load_config
from generation.context_loader import load_context
from generation.rag_loader import load_rag
from generation.prompt_builder import build_system_instruction, build_user_prompt
from generation.pdf_extractor import load_pdf
from generation.pipeline import run_pipeline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the AAS generation pipeline.")
    parser.add_argument("--config", type=Path, default=None,
                        help="Path to config.yaml (defaults to generation/config.yaml)")
    args = parser.parse_args(argv)

    cfg = load_config(args.config)

    print(f"\n=== AAS Generation Pipeline ===")
    print(f"Asset   : {cfg.asset_name}")
    print(f"Provider: {cfg.provider}  |  Model(s): {', '.join(cfg.models)}")
    print(f"Mode    : {cfg.generation_mode}")
    print(f"Submodels: {', '.join(cfg.submodels)}\n")

    print("Loading context files...")
    context_text = load_context(cfg)

    print("\nLoading RAG documents...")
    rag_text_blocks, rag_gemini_parts = load_rag(cfg)

    print("\nLoading PDF (if configured)...")
    pdf_base64, pdf_text = load_pdf(cfg)

    system_instruction = build_system_instruction(cfg, context_text, rag_text_blocks)
    user_prompt = build_user_prompt(cfg, pdf_base64, pdf_text)

    print(f"\nSystem instruction : {len(system_instruction):,} chars")
    print(f"User prompt        : {len(user_prompt):,} chars")
    print(f"Max attempts       : {cfg.max_attempts}")
    print("\nRunning pipeline...\n")

    aas_json, conforms, issues, attempts = run_pipeline(
        cfg=cfg,
        system_instruction=system_instruction,
        user_prompt=user_prompt,
        pdf_base64=pdf_base64,
        rag_gemini_parts=rag_gemini_parts,
    )

    cfg.output_json.parent.mkdir(parents=True, exist_ok=True)
    cfg.output_json.write_text(aas_json, encoding="utf-8")
    print(f"\nAAS JSON  -> {cfg.output_json}")

    cfg.output_issues.parent.mkdir(parents=True, exist_ok=True)
    cfg.output_issues.write_text(json.dumps(issues, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Issues    -> {cfg.output_issues}")

    print(f"\n=== Summary ===")
    print(f"Conforms : {conforms}")
    print(f"Attempts : {attempts}")
    print(f"Issues   : {len(issues)}")

    if issues and not conforms:
        print("\nFirst 5 issues:")
        for issue in issues[:5]:
            sev = issue.get("severity", "?")
            msg = issue.get("message", "")[:120]
            print(f"  [{sev}] {msg}")

    return 0 if conforms else 1


if __name__ == "__main__":
    sys.exit(main())
