from __future__ import annotations

import json
import tempfile
from pathlib import Path

from .config import Config
from .profile_structure import normalize_profile_for_builder
from .text_parsing import extract_outer_json_object


def profile_document_to_aas_json(document: dict[str, Any], cfg: Config) -> str:
    normalized = normalize_profile_for_builder(document, cfg)

    try:
        from .AAS_generation.cli.generate_aas import AASGenerator
    except Exception as exc:
        raise RuntimeError(f"Unable to import AAS generation builder: {exc}") from exc

    with tempfile.TemporaryDirectory() as tmp_dir:
        config_path = Path(tmp_dir) / "profile.json"
        config_path.write_text(json.dumps(normalized, indent=2, ensure_ascii=False), encoding="utf-8")
        generator = AASGenerator(str(config_path), base_url_override=cfg.base_url)
        aas_dict = generator.generate_system(system_id="unused", config=normalized)

    return json.dumps(aas_dict, indent=2, ensure_ascii=False)


def profile_json_text_to_aas_json(profile_text: str, cfg: Config) -> tuple[str, str]:
    cleaned = extract_outer_json_object(profile_text)

    parsed = json.loads(cleaned)
    if not isinstance(parsed, dict):
        raise ValueError("Profile JSON must be an object at top-level.")

    return profile_document_to_aas_json(parsed, cfg), cleaned
