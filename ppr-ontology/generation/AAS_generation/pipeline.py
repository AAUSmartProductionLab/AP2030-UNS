"""
Generation + validation retry loop.
Orchestrates: build conversation -> call LLM -> parse -> validate -> retry.
Returns the final (aas_json, conforms, issues, attempts).
"""
from __future__ import annotations

import json
import re
import tempfile
import time
from pathlib import Path

from ..config import Config
from ..AAS_builder import profile_json_text_to_aas_json
from ..json_description_generation import profile_json_text_to_document, validate_profile_document
from ..llm_client import call_llm
from ..prompt_builder import build_retry_message
from ..validator import run_shacl
from ..json_description_generation import strip_code_fences


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1:
        text = text[first_brace:last_brace + 1]
    return text


def run_pipeline(
    cfg: Config,
    system_instruction: str,
    user_prompt: str,
    pdf_base64: str | None,
    rag_gemini_parts: list[dict],
) -> tuple[str, bool, list[dict], int]:
    model_idx = 0
    aas_json = ""
    conforms = False
    issues: list[dict] = []
    metamodel_issues: list[dict] = []
    ontology_issues: list[dict] = []
    attempt = 0

    if cfg.provider == "gemini":
        first_parts: list[dict] = []
        first_parts.extend(rag_gemini_parts)
        if pdf_base64:
            first_parts.append({"inline_data": {"mime_type": "application/pdf", "data": pdf_base64}})
        first_parts.append({"text": user_prompt})
        gemini_contents: list[dict] = [{"role": "user", "parts": first_parts}]
        groq_history: list[dict] = []
    else:
        gemini_contents = []
        groq_history = [{"role": "user", "content": user_prompt}]

    with tempfile.TemporaryDirectory() as _tmp:
        tmp_dir = Path(_tmp)

        while attempt < cfg.max_attempts:
            attempt += 1
            print(f"\n  -- Attempt {attempt}/{cfg.max_attempts} " + "-" * 30)

            raw_text, model_idx = call_llm(
                provider=cfg.provider,
                api_key=cfg.api_key,
                models=cfg.models,
                model_idx=model_idx,
                system_instruction=system_instruction,
                gemini_contents=gemini_contents if cfg.provider == "gemini" else None,
                groq_history=groq_history if cfg.provider != "gemini" else None,
            )

            if not raw_text:
                attempt -= 1
                continue

            if cfg.provider == "gemini":
                gemini_contents.append({"role": "model", "parts": [{"text": raw_text}]})
            else:
                groq_history.append({"role": "assistant", "content": raw_text})

            if cfg.generation_mode == "json-description":
                raw_text = strip_code_fences(raw_text)
                aas_json = raw_text
            else:
                raw_text = _strip_fences(raw_text)
                aas_json = raw_text

            verify_count = len(re.findall(r'\[VERIFY:', raw_text))
            print(f"  Response: {len(raw_text):,} chars" + (f"  |  [VERIFY] markers: {verify_count}" if verify_count else ""))

            if cfg.generation_mode == "json-description":
                try:
                    document = profile_json_text_to_document(raw_text)
                except Exception as exc:
                    print(f"  Profile JSON parse FAILED: {exc}")
                    issues = [{"severity": "Violation", "message": f"Profile JSON parse failed: {exc}"}]
                    metamodel_issues = issues
                    ontology_issues = []
                    conforms = False
                else:
                    if isinstance(document, dict) and "assetAdministrationShells" in document:
                        issues = [{
                            "severity": "Violation",
                            "message": "LLM returned full AAS JSON. In json-description mode, return profile JSON only.",
                        }]
                        metamodel_issues = issues
                        ontology_issues = []
                        conforms = False
                        print("  Full AAS JSON detected in json-description mode — requesting profile JSON instead.")
                    else:
                        profile_issues = validate_profile_document(document, cfg)
                        metamodel_issues = [{"severity": "Violation", "message": message} for message in profile_issues]
                        if metamodel_issues:
                            ontology_issues = []
                            issues = [*metamodel_issues]
                            conforms = False
                            print(f"  Profile JSON checks: conforms={conforms}, total_issues={len(issues)}")
                        else:
                            try:
                                aas_json, _ = profile_json_text_to_aas_json(raw_text, cfg)
                            except Exception as exc:
                                print(f"  Profile-to-AAS conversion FAILED: {exc}")
                                issues = [{"severity": "Violation", "message": f"Profile to AAS conversion failed: {exc}"}]
                                metamodel_issues = issues
                                ontology_issues = []
                                conforms = False
                            else:
                                print("  Profile conversion OK — running metamodel + ontology validation...")
                                t0 = time.time()
                                conforms, issues, metamodel_issues, ontology_issues = run_shacl(aas_json, tmp_dir)
                                print(f"  Validation: conforms={conforms}, total_issues={len(issues)}  ({time.time()-t0:.1f}s)")
                                print(f"    Metamodel issues: {len(metamodel_issues)}  |  Ontology issues: {len(ontology_issues)}")
            else:
                try:
                    json.loads(raw_text)
                except json.JSONDecodeError as exc:
                    print(f"  JSON parse FAILED: {exc}")
                    issues = [{"severity": "Violation", "message": f"Not valid JSON: {exc}"}]
                    conforms = False
                else:
                    print("  JSON parse OK — running metamodel + ontology validation...")
                    t0 = time.time()
                    conforms, issues, metamodel_issues, ontology_issues = run_shacl(raw_text, tmp_dir)
                    print(f"  Validation: conforms={conforms}, total_issues={len(issues)}  ({time.time()-t0:.1f}s)")
                    print(f"    Metamodel issues: {len(metamodel_issues)}  |  Ontology issues: {len(ontology_issues)}")

            if conforms:
                print("  Validation passed!")
                break

            if metamodel_issues:
                print("  Metamodel validation issues:")
                for issue in metamodel_issues[:10]:
                    print(f"    [{issue.get('severity','?')}] {issue.get('message','')[:120]}")
                if len(metamodel_issues) > 10:
                    print(f"    ... and {len(metamodel_issues) - 10} more")

            if ontology_issues:
                print("  Ontology validation issues:")
                for issue in ontology_issues[:10]:
                    print(f"    [{issue.get('severity','?')}] {issue.get('message','')[:120]}")
                if len(ontology_issues) > 10:
                    print(f"    ... and {len(ontology_issues) - 10} more")

            if attempt < cfg.max_attempts:
                retry_msg = build_retry_message(
                    cfg,
                    attempt,
                    cfg.max_attempts,
                    metamodel_issues,
                    ontology_issues,
                )
                if cfg.provider == "gemini":
                    gemini_contents.append({"role": "user", "parts": [{"text": retry_msg}]})
                else:
                    groq_history.append({"role": "user", "content": retry_msg})

    return aas_json, conforms, issues, attempt
