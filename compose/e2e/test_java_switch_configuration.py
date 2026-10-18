"""Offline configuration contracts. These tests never start a service or device."""

import json
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(params=["docker-compose.yml", "compose/docker-compose.e2e.yml"])
def stack(request):
    result = subprocess.run(
        ["docker", "compose", "--env-file", "/dev/null", "-f", request.param,
         "config", "--format", "json"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


def test_one_shared_java_service_discovers_repository_and_follows_mqtt_events(stack):
    services = stack["services"]
    assert "dmp-management-node" not in services
    dmp = services["dmp"]
    assert dmp["image"] == "dmp:java"
    assert dmp["build"]["context"] == str(ROOT / "aas-camel-dmp/dmp.component")
    assert dmp.get("network_mode") != "host"
    assert not dmp.get("volumes")
    settings = dmp["environment"]
    assert settings["DMP_MANAGED_AAS_REPOSITORY_URI"] == "http://aas-env:8081"
    assert settings["DMP_MANAGED_EVENT_TRANSPORT"] == "mqtt"
    assert not {"DMP_MANAGED_KAFKA_BROKERS", "DMP_MANAGED_CONTROL_TOPIC"} & settings.keys()
    assert settings["DMP_MANAGED_MQTT_BROKER_URI"].startswith("tcp://")
    assert not settings.get("DMP_MANAGED_AIMC_IDS")
    assert not {"DMP_MANAGED_RECONCILIATION", "DMP_MANAGED_OWNER_AAS_IDS", "DMP_MANAGED_REPAIR_INTERVAL_MS"} & settings.keys()
    assert not {"DMP_CONFIG_ROOT", "MANAGED_ASSETS_FILE", "DMP_IMAGE"} & settings.keys()
    assert "DATABRIDGE_HEALTH_PORT" not in settings  # the DMP listens on 8080 by default (DMP_HTTP_PORT)
    assert len(dmp["ports"]) == 1
    assert dmp["ports"][0]["target"] == 8080
    assert dmp["ports"][0]["host_ip"] == "127.0.0.1"
    assert "kafka" not in services
    assert services["aas-env"]["environment"].get("BASYX_FEATURE_KAFKA_ENABLED", "false") == "false"
    assert services["aas-env"]["environment"]["BASYX_SUBMODELREPOSITORY_FEATURE_MQTT_ENABLED"] == "true"


def test_simulation_and_registration_remain_python(stack):
    services = stack["services"]
    assert "stoppering_station" in services
    assert services["registration-service"]["command"][0] == "python"
    assert services["registration-service"]["build"]["context"] == str(ROOT / "Registration_Service")


def test_bootstrap_preserves_authored_resources_and_does_not_install_maven_artifacts():
    script = (ROOT / "compose/e2e/bootstrap.sh").read_text()
    assert "management-node/_aas_model" not in script
    assert "generate_e2e_config" not in script
    assert "write_text(" not in script
    assert "mvn -o -B -Ddocker.skip=true -DskipTests -pl dmp.component -am" in script
    assert "clean package dependency:copy-dependencies" in script
    assert " install " not in script
    assert "/management/status" in script
    assert 's.get("converged")' in script


def test_e2e_native_addresses_use_uri_valid_bridge_hosts():
    config = json.loads((ROOT / "AASDescriptions/Resource/configs/syntegonStoppering.e2e.json").read_text())
    addresses = []

    def visit(value):
        if isinstance(value, dict):
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
        elif isinstance(value, str) and value.startswith(("mqtt://", "opc.tcp://")):
            addresses.append(value)

    visit(config)
    assert set(addresses) == {
        "mqtt://mosquitto:1883/NN/Nybrovej/InnoLab/Stoppering",
        "opc.tcp://stoppering-station:4840/stoppering/",
    }


@pytest.mark.parametrize("name,count", [
    ("syntegonStoppering.main.json", 5),
    ("syntegonStoppering.e2e.json", 7),
    ("syntegonDispensing.json", 8),
])
def test_selected_profiles_retire_proxies_not_native_write_capabilities(name, count):
    config = json.loads((ROOT / "AASDescriptions/Resource/configs" / name).read_text())
    mappings = config["asset_interfaces_mapping_configuration"]["MappingConfigurations"]["value"]
    names = {mapping["id_short"] for mapping in mappings}
    assert len(mappings) == count
    assert not names & {"ParameterWriteMqtt", "ParameterWriteOpcua", "StationStateTimer"}
    assert "writeproperty" in json.dumps(config["asset_interfaces_description"])
    assert "Parameter" in config["variables"]["variable"]
    if name.endswith(".e2e.json"):
        assert {"StopperingOpcua", "HaltOpcua", "OccupyOpcua", "ReleaseOpcua"} <= names
        assert not names & {"Stoppering", "Halt", "Occupy", "Release"}
        assert {"MeasurementEvent", "MeasurementTimer"} <= names


@pytest.mark.parametrize("name", [
    "syntegonStoppering.json", "syntegonStoppering.main.json",
    "syntegonStoppering.e2e.json", "syntegonDispensing.json",
])
def test_checked_in_operation_addresses_share_one_origin(name):
    model = json.loads((ROOT / "AASDescriptions/Resource/configs" / name).read_text())
    assert "delegation_base" not in model
    qualifiers = []

    def visit(value):
        if isinstance(value, dict):
            if value.get("type_") == "invocationDelegation":
                qualifiers.append(value["value"])
            assert value.get("type_") != "writeDelegation"
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(model)
    assert qualifiers, name
    for address in qualifiers:
        assert address.startswith(f"http://dmp:8080/operations/{model['id_short']}/")
        assert "{" not in address and "}" not in address
