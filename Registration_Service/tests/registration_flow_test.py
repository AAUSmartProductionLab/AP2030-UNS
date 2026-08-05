#!/usr/bin/env python3
"""
Registration Service Integration Test

Tests all components of the registration flow against the current
ResourceTypeAAS (JSON) pipeline:

1. Config parsing (parse_config_file + extractors)
2. topics.json generation
3. DataBridge config generation
4. AAS generation (build_from_json → BaSyx store)
5. Full registration (optional - requires BaSyx)

Runs under pytest (``python -m pytest tests/registration_flow_test.py``) or
standalone (``python tests/registration_flow_test.py``).
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

# Add repo + src to path (so the script works standalone too)
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))
sys.path.insert(0, str(_HERE.parent / "third_party" / "aas_pydantic"))

from src import (  # noqa: E402
    BaSyxConfig,
    TopicsGenerator,
    DataBridgeFromConfig,
    UnifiedRegistrationService,
)
from src.config_parser import (  # noqa: E402
    parse_config_file,
    extract_mqtt_endpoint,
    extract_actions,
    extract_properties,
    extract_operation_delegation_entry,
)
from src.aas_idta.builder import build_from_json  # noqa: E402

# The only current Resource config (JSON, ResourceTypeAAS schema).
CONFIG_PATH = (
    _HERE.parent.parent
    / "AASDescriptions"
    / "Resource"
    / "configs"
    / "syntegonStoppering.json"
)


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def config_path() -> Path:
    if not CONFIG_PATH.exists():
        pytest.skip(f"config not found: {CONFIG_PATH}")
    return CONFIG_PATH


@pytest.fixture(scope="module")
def asset(config_path: Path):
    return parse_config_file(str(config_path))


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Config parsing
# ═══════════════════════════════════════════════════════════════════════════════

def test_config_parsing(asset):
    assert asset.id_short == "syntegonStopperingSystemAAS"
    assert asset.id.startswith("https://")

    mqtt = extract_mqtt_endpoint(asset)
    assert mqtt["broker_host"], "broker host must be parsed"
    assert mqtt["base_topic"], "base topic must be parsed"

    actions = extract_actions(asset)
    assert {a["name"] for a in actions} >= {"Stoppering", "Halt", "Occupy", "Release"}

    properties = extract_properties(asset)
    assert {p["name"] for p in properties} == {"StationState"}

    delegation = extract_operation_delegation_entry(asset)
    assert "Stoppering" in delegation["skills"]
    skill = delegation["skills"]["Stoppering"]
    assert skill["command_topic"]
    assert skill.get("response_topic")


# ═══════════════════════════════════════════════════════════════════════════════
# 2. topics.json generation
# ═══════════════════════════════════════════════════════════════════════════════

def test_topics_generation(config_path: Path, tmp_path: Path):
    output_path = tmp_path / "topics.json"
    generator = TopicsGenerator(str(output_path))
    assert generator.add_from_config_file(str(config_path))
    generator.save()

    topics = json.loads(output_path.read_text())
    assert topics, "topics.json must not be empty"
    asset_id, asset_data = next(iter(topics.items()))
    assert asset_data.get("base_topic")
    assert len(asset_data.get("skills", {})) >= 4


# ═══════════════════════════════════════════════════════════════════════════════
# 3. DataBridge config generation
# ═══════════════════════════════════════════════════════════════════════════════

def test_databridge_generation(config_path: Path, tmp_path: Path):
    generator = DataBridgeFromConfig(mqtt_broker="hivemq-broker", mqtt_port=1883)
    assert generator.add_from_config_file(str(config_path))
    counts = generator.save_configs(str(tmp_path))

    assert counts.get("routes", 0) > 0
    for filename in (
        "mqttconsumer.json",
        "jsonatatransformer.json",
        "aasserver.json",
        "routes.json",
    ):
        assert (tmp_path / filename).exists(), f"missing {filename}"


# ═══════════════════════════════════════════════════════════════════════════════
# 4. AAS generation
# ═══════════════════════════════════════════════════════════════════════════════

def test_aas_generation(config_path: Path):
    store = build_from_json(str(config_path))

    shells = [o for o in store if o.__class__.__name__ == "AssetAdministrationShell"]
    submodels = [o for o in store if o.__class__.__name__ == "Submodel"]

    assert len(shells) == 1
    shell = shells[0]
    assert shell.id_short == "syntegonStopperingSystemAAS"
    assert shell.id

    sm_ids = {sm.id_short for sm in submodels}
    assert sm_ids >= {
        "Nameplate",
        "AssetInterfacesDescription",
        "ControlComponentInstance",
        "Variables",
        "Parameters",
    }

    # AID must carry the MQTT actions + the WoT op field on forms
    aid = next(sm for sm in submodels if sm.id_short == "AssetInterfacesDescription")
    op_count = 0

    def _walk(el):
        nonlocal op_count
        if getattr(el, "id_short", "") == "op":
            op_count += 1
        value = getattr(el, "value", None)
        items = list(value) if hasattr(value, "__iter__") and not isinstance(value, (str, bytes)) else []
        for child in items:
            _walk(child)

    for el in aid.submodel_element:
        _walk(el)
    assert op_count >= 4, "each action form must carry an op Property"

    # Parameters.Location must carry its children (x/y/yaw)
    parameters = next(sm for sm in submodels if sm.id_short == "Parameters")
    location = next(
        (el for el in parameters.submodel_element if el.id_short == "Location"),
        None,
    )
    assert location is not None
    child_ids = {c.id_short for c in location.value}
    assert {"x", "y", "yaw"} <= child_ids


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Full registration (optional - requires BaSyx)
# ═══════════════════════════════════════════════════════════════════════════════

def test_full_registration(config_path: Path, basyx_url: str = "http://aas-env:8081"):
    try:
        import requests
        try:
            response = requests.get(f"{basyx_url}/shells", timeout=5)
            if response.status_code not in [200, 401]:
                pytest.skip(f"BaSyx returned status {response.status_code}")
        except requests.exceptions.ConnectionError:
            pytest.skip(f"Cannot connect to BaSyx at {basyx_url}")
    except ImportError:
        pytest.skip("requests not installed")

    service = UnifiedRegistrationService(
        config=BaSyxConfig(base_url=basyx_url),
        mqtt_broker="192.168.0.104",
        mqtt_port=1883,
        delegation_service_url="http://192.168.0.104:8087",
    )
    assert service.register_from_config(str(config_path))


# ═══════════════════════════════════════════════════════════════════════════════
# Standalone CLI (pytest-compatible — pytest skips non-test helpers)
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Test Registration Service Flow")
    parser.add_argument("--config", default=str(CONFIG_PATH))
    parser.add_argument("--with-basyx", action="store_true")
    parser.add_argument("--basyx-url", default="http://aas-env:8081")
    parser.add_argument("--keep-output", action="store_true")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"Config file not found: {config_path}")
        sys.exit(1)

    output_dir = Path(tempfile.mkdtemp(prefix="reg_test_"))
    results = {}
    try:
        asset = parse_config_file(str(config_path))
        results["config_parsing"] = "PASSED"
        print("config parsing: PASSED")

        tg = TopicsGenerator(str(output_dir / "topics.json"))
        results["topics_generation"] = "PASSED" if tg.add_from_config_file(str(config_path)) else "FAILED"
        print(f"topics generation: {results['topics_generation']}")

        dbg = DataBridgeFromConfig(mqtt_broker="hivemq-broker", mqtt_port=1883)
        counts = dbg.add_from_config_file(str(config_path))
        dbg.save_configs(str(output_dir))
        results["databridge_generation"] = "PASSED" if counts.get("routes", 0) > 0 else "FAILED"
        print(f"databridge generation: {results['databridge_generation']}")

        store = build_from_json(str(config_path))
        shells = [o for o in store if o.__class__.__name__ == "AssetAdministrationShell"]
        submodels = [o for o in store if o.__class__.__name__ == "Submodel"]
        results["aas_generation"] = "PASSED" if shells and len(submodels) >= 5 else "FAILED"
        print(f"aas generation: {results['aas_generation']} ({len(shells)} shells, {len(submodels)} submodels)")

        if args.with_basyx:
            service = UnifiedRegistrationService(
                config=BaSyxConfig(base_url=args.basyx_url),
                mqtt_broker="192.168.0.104", mqtt_port=1883,
                delegation_service_url="http://192.168.0.104:8087",
            )
            results["full_registration"] = "PASSED" if service.register_from_config(str(config_path)) else "FAILED"
            print(f"full registration: {results['full_registration']}")
    finally:
        if not args.keep_output:
            shutil.rmtree(output_dir, ignore_errors=True)

    failed = [k for k, v in results.items() if v != "PASSED"]
    print(f"\nResults: {len(results) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
