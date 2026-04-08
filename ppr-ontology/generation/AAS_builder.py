from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import yaml

from .config import Config
from .json_description_generation import strip_code_fences


def _selected_profile_section_keys(cfg: Config) -> set[str]:
    selected = {name.strip().lower() for name in cfg.submodels}
    allowed: set[str] = {
        "idShort",
        "id",
        "globalAssetId",
        "derivedFrom",
        "assetType",
        "serialNumber",
        "location",
    }

    if "nameplate" in selected or "digitalnameplate" in selected:
        allowed.add("DigitalNameplate")
    if "hierarchicalstructures" in selected:
        allowed.add("HierarchicalStructures")
    if "aid" in selected or "assetinterfacesdescription" in selected:
        allowed.update({"AssetInterfacesDescription", "AssetInterfaceDescription", "AID"})
    if "operationaldata" in selected or "variables" in selected:
        allowed.update({"OperationalData", "Variables"})
    if "parameters" in selected:
        allowed.add("Parameters")
    if "capabilities" in selected:
        allowed.add("Capabilities")
    if "skills" in selected:
        allowed.add("Skills")

    return allowed


def _prune_profile_sections(profile: dict[str, Any], cfg: Config) -> dict[str, Any]:
    if not profile:
        return profile

    system_name = next(iter(profile.keys()))
    body = profile.get(system_name)
    if not isinstance(body, dict):
        return profile

    allowed = _selected_profile_section_keys(cfg)
    pruned_body = {k: v for k, v in body.items() if k in allowed}
    return {system_name: pruned_body}


def _normalize_profile_for_builder(document: Any, cfg: Config) -> dict[str, Any]:
    if not isinstance(document, dict):
        raise ValueError("Description output must be a mapping/object at top-level.")

    if len(document) == 1 and isinstance(next(iter(document.values())), dict):
        system_name = next(iter(document.keys()))
        system_config = dict(next(iter(document.values())))
    else:
        system_name = f"{cfg.asset_name}AAS"
        system_config = dict(document)

    filtered = _prune_profile_sections({system_name: system_config}, cfg)
    system_config = dict(filtered.get(system_name, {}))

    if "AssetInterfaceDescription" in system_config and "AssetInterfacesDescription" not in system_config:
        system_config["AssetInterfacesDescription"] = system_config["AssetInterfaceDescription"]

    if "AID" in system_config and "AssetInterfacesDescription" not in system_config:
        system_config["AssetInterfacesDescription"] = system_config["AID"]

    if "OperationalData" in system_config and "Variables" not in system_config:
        system_config["Variables"] = system_config["OperationalData"]

    if "DigitalNameplate" not in system_config:
        system_config["DigitalNameplate"] = {
            "ManufacturerName": "[VERIFY: manufacturer name]",
            "SerialNumber": str(system_config.get("serialNumber", "[VERIFY: serial number]")),
            "ManufacturerProductDesignation": cfg.asset_name,
            "DateOfManufacture": "[VERIFY: manufacture date YYYY-MM-DD]",
        }

    return {system_name: system_config}


def profile_document_to_aas_json(document: dict[str, Any], cfg: Config) -> str:
    normalized = _normalize_profile_for_builder(document, cfg)

    try:
        from .AAS_generation.cli.generate_aas import AASGenerator
    except Exception as exc:
        raise RuntimeError(f"Unable to import generation_2 builder: {exc}") from exc

    with tempfile.TemporaryDirectory() as tmp_dir:
        config_path = Path(tmp_dir) / "profile.json"
        config_path.write_text(json.dumps(normalized, indent=2, ensure_ascii=False), encoding="utf-8")
        generator = AASGenerator(str(config_path), base_url_override=cfg.base_url)
        aas_dict = generator.generate_system(system_id="unused", config=normalized)

    return json.dumps(aas_dict, indent=2, ensure_ascii=False)


def profile_json_text_to_aas_json(profile_text: str, cfg: Config) -> tuple[str, str]:
    cleaned = strip_code_fences(profile_text)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end >= start:
        cleaned = cleaned[start : end + 1]

    parsed = json.loads(cleaned)
    if not isinstance(parsed, dict):
        raise ValueError("Profile JSON must be an object at top-level.")

    return profile_document_to_aas_json(parsed, cfg), cleaned
