"""Authored resources serialize through the registration pipeline.

Java eligibility of the published models is covered by the DMP's own contract-fixture
tests; the former ``--compare`` black-box mode of the runtime was removed.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]


def _serialize_resource(config_path: Path) -> dict:
    """Use the registration model pipeline without importing service startup."""
    for import_path in (ROOT / "aas-model/src", ROOT / "Registration_Service"):
        if str(import_path) not in sys.path:
            sys.path.insert(0, str(import_path))
    from aas_model.builder import build_from_model
    from aas_pydantic.convert_util import strip_temp_id_short_attributes
    from basyx.aas.adapter.json import json_serialization

    parser_path = ROOT / "Registration_Service/src/config_parser.py"
    parser_spec = importlib.util.spec_from_file_location("resource_compat_config_parser", parser_path)
    parser = importlib.util.module_from_spec(parser_spec)
    parser_spec.loader.exec_module(parser)

    asset = parser.parse_config_file(str(config_path))
    store = build_from_model(asset)
    strip_temp_id_short_attributes(store)
    return json.loads(json_serialization.object_store_to_json(store))


def test_python_resource_export_serializes_through_registration(tmp_path):
    exporter = ROOT / "Registration_Service/scripts/export_resource_config.py"
    result = subprocess.run(
        [sys.executable, str(exporter)], capture_output=True, text=True, check=True,
    )
    config_path = tmp_path / "resource.json"
    config_path.write_text(result.stdout, encoding="utf-8")

    document = _serialize_resource(config_path)

    assert len(document["assetAdministrationShells"]) == 1
    assert document["assetAdministrationShells"][0]["idShort"] == "syntegonStopperingSystemAAS"
    assert len(document["submodels"]) == 7
    assert "CapabilityDescription" in {submodel["idShort"] for submodel in document["submodels"]}
    assert config_path.read_text(encoding="utf-8") == result.stdout
