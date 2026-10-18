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


def test_one_shared_java_service_discovers_repository_and_follows_kafka_events(stack):
    services = stack["services"]
    assert "dmp-management-node" not in services
    dmp = services["dmp"]
    assert dmp["image"] == "dmp:java"
    assert dmp["build"]["context"] == str(ROOT / "aas-camel-dmp/dmp.component")
    assert dmp.get("network_mode") != "host"
    assert not dmp.get("volumes")
    settings = dmp["environment"]
    assert settings["DMP_MANAGED_AAS_REPOSITORY_URI"] == "http://aas-env:8081"
    assert settings["DMP_MANAGED_EVENT_TRANSPORT"] == "kafka"
    assert settings["DMP_MANAGED_KAFKA_BROKERS"] == "kafka:9092"
    assert settings["DMP_MANAGED_CONTROL_TOPIC"] == "submodel-events"
    assert not any(name.startswith("DMP_MANAGED_MQTT_") for name in settings)
    assert not settings.get("DMP_MANAGED_AIMC_IDS")
    assert not {"DMP_MANAGED_RECONCILIATION", "DMP_MANAGED_OWNER_AAS_IDS", "DMP_MANAGED_REPAIR_INTERVAL_MS"} & settings.keys()
    assert not {"DMP_CONFIG_ROOT", "MANAGED_ASSETS_FILE", "DMP_IMAGE"} & settings.keys()
    assert "DATABRIDGE_HEALTH_PORT" not in settings  # the DMP listens on 8080 by default (DMP_HTTP_PORT)
    assert len(dmp["ports"]) == 1
    assert dmp["ports"][0]["target"] == 8080
    assert dmp["ports"][0]["host_ip"] == "127.0.0.1"
    assert services["aas-env"]["environment"]["BASYX_FEATURE_KAFKA_ENABLED"] == "true"
    assert services["aas-env"]["environment"]["SPRING_KAFKA_BOOTSTRAP_SERVERS"] == "kafka:9092"
    assert services["aas-env"]["environment"]["BASYX_SUBMODELREPOSITORY_FEATURE_MQTT_ENABLED"] == "false"
    assert services["aas-env"]["environment"]["BASYX_AASREPOSITORY_FEATURE_MQTT_ENABLED"] == "false"


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
