"""Evaluation runner — calls the v2 pipeline directly (no HTTP/SSE) and records
metrics per (equipment × LLM × ablation × repetition) experiment.

Layouts:
  evaluation/equipment/<id>/equipment.yaml          required
  evaluation/equipment/<id>/datasheet.pdf           optional
  evaluation/equipment/<id>/spec.md                 optional, used when no PDF
  evaluation/equipment/<id>/interface.csv|opcua.xml etc.  optional, declared in equipment.yaml
  evaluation/ground_truth/<id>.yaml                 required for metrics

Each completed experiment writes ONE JSON line to `--output`.

Ablation flags
  full           — v2 pipeline as-is (default): templates + RAG + retry on SHACL feedback
  no-feedback    — same context, but max_attempts=1 (no retry — measures one-shot conformance)
  no-templates   — strip per-submodel templates; only minimal preamble
  zero-shot      — strip templates AND RAG (raw LLM with only generic AAS knowledge)

Usage:
  python -m evaluation.run_eval --equipment ca18clc12bpm1 --provider claude \\
      --model claude-opus-4-5-20251101 --ablation full \\
      --output evaluation/results/run_2026-04-25.jsonl

  python -m evaluation.run_eval --matrix evaluation/matrix.yaml \\
      --output evaluation/results/run_2026-04-25.jsonl
"""
from __future__ import annotations

import argparse
import base64
import dataclasses
import json
import os
import shutil
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from generation.config import load_config, Config  # noqa: E402
from generation.context_loader import load_context  # noqa: E402
from generation.rag_loader import load_rag  # noqa: E402
from generation.prompt_builder import build_system_instruction, build_user_prompt  # noqa: E402
from generation.pdf_extractor import extract_pdf_text  # noqa: E402
from generation.v2.pipeline_v2 import run_pipeline as run_pipeline_v2  # noqa: E402
from generation.pipeline import run_pipeline as run_pipeline_v1  # noqa: E402

from evaluation import metrics as M  # noqa: E402


_EVAL_DIR = Path(__file__).resolve().parent
_EQUIPMENT_DIR = _EVAL_DIR / "equipment"
_GROUND_TRUTH_DIR = _EVAL_DIR / "ground_truth"


# --------------------------------------------------------------------- helpers


def _read_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _read_text(path: Path | None) -> str:
    if path is None or not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _read_pdf_base64(path: Path | None) -> str | None:
    if path is None or not path.exists() or path.suffix.lower() != ".pdf":
        return None
    return base64.b64encode(path.read_bytes()).decode("utf-8")


def _interface_summary(equipment: dict, equipment_dir: Path) -> str:
    """Build a textual summary of all interface files for the LLM prompt.

    OPC UA NodeSet XML, CSV register lists, and OpenPLC XML get reduced to a
    compact format that fits in a context window. Real datasheets stay as PDFs.
    """
    blocks: list[str] = []
    for entry in equipment.get("interface_files", []) or []:
        rel = entry.get("path") if isinstance(entry, dict) else None
        if not rel:
            continue
        kind = (entry.get("kind") or "").lower()
        path = (equipment_dir / rel).resolve()
        if not path.exists():
            continue
        if kind.startswith("opcua") or path.suffix.lower() == ".xml":
            xml_text = _read_text(path)
            blocks.append(f"### Interface: {path.name} (OPC UA NodeSet XML)\n```xml\n{xml_text}\n```")
        elif kind.startswith("csv") or path.suffix.lower() == ".csv":
            csv_text = _read_text(path)
            blocks.append(f"### Interface: {path.name} (CSV register / signal list)\n```csv\n{csv_text}\n```")
        elif kind.startswith("openplc") or path.suffix.lower() == ".plcopen":
            xml_text = _read_text(path)
            blocks.append(f"### Interface: {path.name} (OpenPLC / PLCopen XML)\n```xml\n{xml_text}\n```")
        else:
            text = _read_text(path)
            blocks.append(f"### Interface: {path.name}\n```\n{text}\n```")
    return "\n\n".join(blocks)


# --------------------------------------------------------------------- ablations


def _apply_ablation(cfg: Config, ablation: str) -> Config:
    """Return a Config copy with the ablation knobs applied.

    Ablation strategy:
      full           — leave cfg as-is (default). use_rag/use_example/max_attempts read from yaml.
      no-feedback    — max_attempts = 1 (still uses templates + RAG).
      no-templates   — context_dir → minimal-preamble-only stub.
      zero-shot      — no-templates + use_rag=False + use_example=False.
    """
    cfg = dataclasses.replace(cfg)
    if ablation == "full":
        return cfg
    if ablation == "no-feedback":
        cfg.max_attempts = 1
        return cfg
    if ablation in ("no-templates", "zero-shot"):
        # Materialize a minimal context dir on the fly. We keep only the very
        # short generic preamble — no per-submodel templates, no IDTA tables.
        stub_dir = _EVAL_DIR / "_ablation_minimal_context"
        stub_dir.mkdir(exist_ok=True)
        (stub_dir / "00-preamble.md").write_text(
            "# Generation context (minimal — ablation: no-templates)\n\n"
            "Generate an AAS Part 2 v3.1 JSON document for the asset described in the user prompt. "
            "Use the AAS metamodel correctly: assetAdministrationShells, submodels, conceptDescriptions. "
            "Output ONLY a single valid JSON object. Use [VERIFY: reason] only on mandatory fields you cannot determine.\n",
            encoding="utf-8",
        )
        (stub_dir / "shacl-rules.md").write_text("(no domain rules in this ablation)\n", encoding="utf-8")
        (stub_dir / "submodels").mkdir(exist_ok=True)
        cfg.context_dir = stub_dir
        if ablation == "zero-shot":
            cfg.use_rag = False
            cfg.use_example = False
        return cfg
    raise ValueError(f"Unknown ablation: {ablation}")


# --------------------------------------------------------------------- pipeline call


def _run_one(
    *,
    equipment_id: str,
    provider: str,
    model: str | None,
    mode: str,
    ablation: str,
    repetition: int,
    pipeline: str,
) -> dict[str, Any]:
    """Run a single experiment and return its result row."""
    equipment_dir = _EQUIPMENT_DIR / equipment_id
    equipment_yaml = equipment_dir / "equipment.yaml"
    ground_truth_yaml = _GROUND_TRUTH_DIR / f"{equipment_id}.yaml"
    if not equipment_yaml.exists():
        raise FileNotFoundError(f"equipment.yaml missing: {equipment_yaml}")
    if not ground_truth_yaml.exists():
        raise FileNotFoundError(f"ground truth missing: {ground_truth_yaml}")

    equipment = _read_yaml(equipment_yaml)
    ground_truth = _read_yaml(ground_truth_yaml)

    pdf_path = equipment.get("datasheet")
    pdf_full = (equipment_dir / pdf_path).resolve() if pdf_path else None
    spec_md_path = equipment_dir / "spec.md"
    interface_summary = _interface_summary(equipment, equipment_dir)
    spec_text = _read_text(spec_md_path)
    spec_text_combined = "\n\n---\n\n".join(s for s in (spec_text, interface_summary) if s)

    # ------ build a Config tailored to this equipment ------
    base_cfg = load_config()
    cfg = dataclasses.replace(
        base_cfg,
        provider=provider,
        api_key=getattr(base_cfg, f"{provider}_api_key", "") or base_cfg.api_key,
        asset_name=str(equipment.get("asset_name", equipment_id)),
        base_url=str(equipment.get("base_url", base_cfg.base_url)),
        pdf_path=pdf_full,
        submodels=list(equipment.get("selected_submodels", base_cfg.submodels)),
        generation_mode=mode,
        max_attempts=int(equipment.get("max_attempts", base_cfg.max_attempts)),
        models=[model] if model else base_cfg.models,
    )
    cfg = _apply_ablation(cfg, ablation)

    # ------ assemble inputs ------
    pdf_b64 = _read_pdf_base64(pdf_full) if cfg.provider == "gemini" else None
    pdf_text = ""
    if cfg.provider != "gemini" and pdf_full is not None and pdf_full.exists():
        pdf_text = extract_pdf_text(pdf_full, max_chars=cfg.max_pdf_chars)

    rag_gemini_parts, _ = load_rag(cfg) if cfg.use_rag else ([], [])

    system_instruction = build_system_instruction(cfg, load_context(cfg))
    user_prompt = build_user_prompt(
        cfg,
        pdf_b64,
        pdf_text,
        spec_sheet_text=spec_text_combined,
        supplemental_context=interface_summary or None,
    )

    # ------ run ------
    runner = run_pipeline_v1 if pipeline == "v1" else run_pipeline_v2
    log_lines: list[str] = []
    def _capture(msg: str) -> None:
        log_lines.append(msg)
    t0 = time.time()
    error: str | None = None
    aas_json = ""
    conforms = False
    issues: list[dict] = []
    attempts = 0
    try:
        aas_json, conforms, issues, attempts = runner(
            cfg, system_instruction, user_prompt, pdf_b64, rag_gemini_parts,
            progress_callback=_capture,
        )
    except SystemExit as exc:
        error = f"SystemExit: {exc}"
    except Exception as exc:  # pragma: no cover
        error = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
    wallclock = time.time() - t0

    # ------ parse & score ------
    aas_doc: dict = {}
    if aas_json:
        try:
            aas_doc = json.loads(aas_json)
        except Exception as exc:
            error = (error + " | " if error else "") + f"AAS JSON parse failed: {exc}"

    metamodel = [i for i in issues if (i.get("source") == "metamodel" or "metamodel" in i.get("source",""))]
    ontology = [i for i in issues if i.get("source") == "ontology"]
    if not metamodel and not ontology:
        # Fall back: when run_shacl_v2 returned issues without source labels
        metamodel = issues

    metric_row = M.all_metrics(
        aas_doc, ground_truth,
        conforms=conforms,
        metamodel_issues=metamodel,
        ontology_issues=ontology,
        attempts=attempts,
        wallclock_seconds=wallclock,
    )

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "equipment_id": equipment_id,
        "asset_name": cfg.asset_name,
        "protocol": equipment.get("protocol", ""),
        "provider": cfg.provider,
        "model": model or (cfg.models[0] if cfg.models else "default"),
        "mode": cfg.generation_mode,
        "pipeline": pipeline,
        "ablation": ablation,
        "repetition": repetition,
        "max_attempts": cfg.max_attempts,
        "use_rag": cfg.use_rag,
        "use_example": cfg.use_example,
        "metrics": metric_row,
        "error": error,
    }


# --------------------------------------------------------------------- matrix sweep


def _run_matrix(matrix: dict, output: Path) -> None:
    repetitions = int(matrix.get("repetitions", 1))
    equipment_ids = matrix.get("equipment", [])
    configs = matrix.get("configs", [])

    output.parent.mkdir(parents=True, exist_ok=True)
    total = len(equipment_ids) * len(configs) * repetitions
    n = 0
    for rep in range(repetitions):
        for eq in equipment_ids:
            for c in configs:
                n += 1
                tag = f"[{n}/{total}]  {eq}  {c.get('provider')}/{c.get('model','*')}  {c.get('ablation','full')}  rep={rep+1}"
                print(tag)
                try:
                    row = _run_one(
                        equipment_id=eq,
                        provider=c["provider"],
                        model=c.get("model"),
                        mode=c.get("mode", "json-description"),
                        ablation=c.get("ablation", "full"),
                        repetition=rep + 1,
                        pipeline=c.get("pipeline", "v2"),
                    )
                except Exception as exc:
                    row = {
                        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        "equipment_id": eq,
                        "provider": c.get("provider"),
                        "model": c.get("model"),
                        "ablation": c.get("ablation", "full"),
                        "repetition": rep + 1,
                        "metrics": {},
                        "error": f"runner exception: {type(exc).__name__}: {exc}",
                    }
                with output.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"\nWrote {n} result rows to {output}")


# --------------------------------------------------------------------- CLI


def main() -> int:
    p = argparse.ArgumentParser(description="Run evaluation experiments for the v2 AAS pipeline.")
    p.add_argument("--equipment", help="Equipment ID under evaluation/equipment/")
    p.add_argument("--provider", choices=["gemini", "groq", "claude"], default="claude")
    p.add_argument("--model", default=None, help="Specific model id; defaults to config.yaml's first model for the provider.")
    p.add_argument("--mode", choices=["json", "json-description"], default="json-description")
    p.add_argument("--ablation", choices=["full", "no-feedback", "no-templates", "zero-shot"], default="full")
    p.add_argument("--pipeline", choices=["v1", "v2"], default="v2")
    p.add_argument("--repetitions", type=int, default=1)
    p.add_argument("--matrix", type=Path, help="Path to a YAML sweep matrix (overrides single-experiment flags).")
    p.add_argument("--output", type=Path, required=True, help="JSONL output file (appended).")
    args = p.parse_args()

    if args.matrix:
        matrix = _read_yaml(args.matrix)
        _run_matrix(matrix, args.output)
        return 0

    if not args.equipment:
        p.error("either --equipment or --matrix is required")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    for rep in range(args.repetitions):
        print(f"[{rep+1}/{args.repetitions}] {args.equipment}  {args.provider}/{args.model or '*'}  {args.ablation}")
        row = _run_one(
            equipment_id=args.equipment,
            provider=args.provider,
            model=args.model,
            mode=args.mode,
            ablation=args.ablation,
            repetition=rep + 1,
            pipeline=args.pipeline,
        )
        with args.output.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        m = row["metrics"]
        print(
            f"  → conforms={m.get('shacl_conforms')}, sme_coverage={m.get('sme_coverage'):.2f}, "
            f"semanticid_match={m.get('semanticid_exact_match'):.2f}, "
            f"verify_rate={m.get('verify_rate'):.2f}, attempts={m.get('attempts')}, "
            f"wallclock={m.get('wallclock_seconds'):.1f}s"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
