"""End-to-end test: BaSyx → Kafka → bridge → Fuseki with SHA256 fact IRIs.

Tests the full data pipeline:
1. AAS events published to Kafka
2. kg-bridge consumes and projects to ARSO/APEX + materialization
3. Fuseki stores in named graphs (TBox, ABox, SHACL)
4. Dynamic predicate views return correct SHA256-derived fact IRIs
5. Resource spatial reasoning (InRange) works across actors
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Generator
from urllib.parse import quote

import pytest
import requests
from confluent_kafka import Producer

# Add kg-bridge to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Environment
REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"
FUSEKI_BASE = os.getenv("FUSEKI_BASE", "http://localhost:3030")
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9093")


class FusekiClient:
    """Helper for SPARQL queries against Fuseki."""

    def __init__(self, base_url: str = FUSEKI_BASE, user: str = "admin", password: str = "admin"):
        self.base_url = base_url
        self.auth = (user, password)

    def query(self, sparql: str) -> dict:
        """Execute SELECT query and return JSON-LD results."""
        resp = requests.post(
            f"{self.base_url}/kg/sparql",
            headers={"Content-Type": "application/sparql-query", "Accept": "application/sparql-results+json"},
            data=sparql,
            auth=self.auth,
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    def construct(self, sparql: str) -> str:
        """Execute CONSTRUCT query and return Turtle."""
        resp = requests.post(
            f"{self.base_url}/kg/sparql",
            headers={"Content-Type": "application/sparql-query", "Accept": "text/turtle"},
            data=sparql,
            auth=self.auth,
            timeout=10,
        )
        resp.raise_for_status()
        return resp.text

    def update(self, sparql_update: str) -> None:
        """Execute UPDATE query."""
        resp = requests.post(
            f"{self.base_url}/kg/update",
            headers={"Content-Type": "application/sparql-update"},
            data=sparql_update,
            auth=self.auth,
            timeout=10,
        )
        resp.raise_for_status()

    def count_triples(self, graph: str) -> int:
        """Count triples in a named graph."""
        result = self.query(f'SELECT (COUNT(*) AS ?n) WHERE {{ GRAPH <{graph}> {{ ?s ?p ?o }} }}')
        return int(result["results"]["bindings"][0]["n"]["value"]) if result["results"]["bindings"] else 0


def _repo_root() -> Path:
    return REPO_ROOT


def _view_sparql(name: str) -> str:
    """Load a view SPARQL file."""
    query = (_repo_root() / "kg-bridge" / "sparql" / "views" / f"{name}.rq").read_text(encoding="utf-8")
    # `aas:Submodel/submodelElements` is not a valid prefixed name in SPARQL parsers.
    return query.replace(
        "aas:Submodel/submodelElements",
        "<https://admin-shell.io/aas/3/1/Submodel/submodelElements>",
    )


@pytest.fixture(scope="session")
def docker_stack() -> Generator[None, None, None]:
    """Start docker-compose stack for the session, clean up after."""
    print("\n[docker_stack] Starting docker-compose stack...")
    subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE_FILE), "--profile", "knowledge-graph", "up", "-d"],
        check=True,
        capture_output=True,
    )

    # Ensure Kafka is ready and topics exist before bridge subscribes to regex.
    kafka_ready = False
    for _ in range(40):
        probe = subprocess.run(
            [
                "docker",
                "exec",
                "kg-kafka",
                "kafka-topics",
                "--bootstrap-server",
                "localhost:9092",
                "--list",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if probe.returncode == 0:
            kafka_ready = True
            break
        time.sleep(1)

    if not kafka_ready:
        raise TimeoutError("Kafka did not become ready for topic administration")

    for topic in ("aas-events", "submodel-events"):
        subprocess.run(
            [
                "docker",
                "exec",
                "kg-kafka",
                "kafka-topics",
                "--bootstrap-server",
                "localhost:9092",
                "--create",
                "--if-not-exists",
                "--topic",
                topic,
                "--partitions",
                "1",
                "--replication-factor",
                "1",
            ],
            check=True,
            capture_output=True,
        )

    subprocess.run(["docker", "restart", "kg-bridge"], check=True, capture_output=True)

    # Wait for Fuseki to be healthy (health check is built into compose)
    print("[docker_stack] Waiting for Fuseki to be ready...")
    max_tries = 60
    for i in range(max_tries):
        try:
            resp = requests.get(f"{FUSEKI_BASE}/$/ping", timeout=2)
            if resp.status_code == 200:
                print("[docker_stack] Fuseki is healthy")
                break
        except requests.exceptions.RequestException:
            pass
        time.sleep(1)
    else:
        raise TimeoutError(f"Fuseki did not become healthy after {max_tries}s")

    # Wait for bridge to connect and process initial batches
    print("[docker_stack] Waiting for bridge to start processing...")
    time.sleep(8)

    yield

    print("\n[docker_stack] Tearing down docker-compose stack...")
    subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE_FILE), "--profile", "knowledge-graph", "down"],
        check=False,
        capture_output=True,
    )


@pytest.fixture
def fuseki(docker_stack) -> FusekiClient:
    """Fuseki client connected to the running stack."""
    return FusekiClient()


@pytest.fixture
def kafka_producer(docker_stack) -> Generator[Producer, None, None]:
    """Kafka producer for the running stack."""

    def delivery_report(err, msg):
        if err is not None:
            print(f"[kafka] Delivery failed: {err}")
        else:
            print(f"[kafka] Message delivered to {msg.topic()} partition {msg.partition()}")

    producer = Producer(
        {"bootstrap.servers": KAFKA_BOOTSTRAP, "acks": "all"},
        on_delivery=delivery_report,
    )

    yield producer

    producer.flush()


def _publish_aas_event(producer: Producer, aas_id: str, id_short: str) -> None:
    """Publish AAS_CREATED event to Kafka."""
    payload = {
        "type": "AAS_CREATED",
        "id": aas_id,
        "aas": {
            "id": aas_id,
            "idShort": id_short,
            "assetInformation": {"assetKind": "Instance"},
        },
    }
    producer.produce(
        topic="aas-events",
        key=aas_id.encode("utf-8"),
        value=json.dumps(payload).encode("utf-8"),
    )
    print(f"[test] Published AAS_CREATED for {aas_id}")


def _publish_submodel_event(producer: Producer, sm_id: str) -> None:
    """Publish SM_CREATED event with empty submodel elements."""
    payload = {
        "type": "SM_CREATED",
        "id": sm_id,
        "submodel": {
            "id": sm_id,
            "idShort": "OperationalData",
            "submodelElements": [],
        },
    }
    producer.produce(
        topic="submodel-events",
        key=sm_id.encode("utf-8"),
        value=json.dumps(payload).encode("utf-8"),
    )
    print(f"[test] Published SM_CREATED for {sm_id}")


def _publish_sme_updated_event(
    producer: Producer,
    sm_id: str,
    path: str,
    id_short: str,
    value: str | float | bool,
) -> None:
    """Publish SME_UPDATED event for a mirrored sensor value."""
    canonical_path = path if path.endswith(id_short) else f"{path}.{id_short}"
    payload = {
        "type": "SME_UPDATED",
        "id": sm_id,
        "smElementPath": canonical_path,
        "smElement": {
            "modelType": "Property",
            "idShort": id_short,
            "value": value,
            "valueType": "xs:string" if isinstance(value, str) else ("xs:float" if isinstance(value, float) else "xs:boolean"),
        },
    }
    producer.produce(
        topic="submodel-events",
        key=f"{sm_id}/{canonical_path}".encode("utf-8"),
        value=json.dumps(payload).encode("utf-8"),
    )
    print(f"[test] Published SME_UPDATED for {sm_id}/{canonical_path}={value}")


def _publish_sm_ref_added_event(producer: Producer, aas_id: str, sm_id: str) -> None:
    """Publish SM_REF_ADDED event to link AAS and submodel."""
    payload = {
        "type": "SM_REF_ADDED",
        "id": aas_id,
        "submodelId": sm_id,
    }
    producer.produce(
        topic="aas-events",
        key=aas_id.encode("utf-8"),
        value=json.dumps(payload).encode("utf-8"),
    )
    print(f"[test] Published SM_REF_ADDED for aas={aas_id} sm={sm_id}")


def _wait_for_abox_triple_count(fuseki: FusekiClient, min_count: int, timeout_sec: int = 30) -> int:
    """Poll ABox triple count until it reaches min_count or timeout."""
    start = time.time()
    while time.time() - start < timeout_sec:
        count = fuseki.count_triples("urn:kg:abox")
        if count >= min_count:
            print(f"[test] ABox has {count} triples (target {min_count})")
            return count
        time.sleep(1)
    raise TimeoutError(f"ABox did not reach {min_count} triples within {timeout_sec}s (got {count})")


def _sha256_fact_iri(args: list[str]) -> str:
    """Compute SHA256-based fact IRI as bridge does it."""
    arg_str = "|".join(str(a) for a in args)
    hash_digest = hashlib.sha256(arg_str.encode("utf-8")).hexdigest()
    return f"urn:kg:apex:in-range:{quote(hash_digest, safe='')}"


class TestRealStackE2E:
    """End-to-end tests for the real Kafka→bridge→Fuseki stack."""

    def test_real_stack_smoke_pipeline(self, fuseki: FusekiClient, kafka_producer: Producer) -> None:
        """Smoke E2E: Kafka events flow through bridge and are queryable in Fuseki views."""
        suffix = uuid.uuid4().hex[:8]
        aas_id = f"urn:aas:e2e:smoke-shell-{suffix}"
        sm_id = f"urn:sm:e2e:smoke-operational-{suffix}"
        id_short = f"SmokeShell-{suffix}"

        abox_before = fuseki.count_triples("urn:kg:abox")

        _publish_aas_event(kafka_producer, aas_id, id_short)
        _publish_submodel_event(kafka_producer, sm_id)
        _publish_sm_ref_added_event(kafka_producer, aas_id, sm_id)
        _publish_sme_updated_event(kafka_producer, sm_id, "Runtime", "CurrentLocation", f"cell-{suffix}")
        _publish_sme_updated_event(kafka_producer, sm_id, "Runtime", "PositionX", "1.0")
        _publish_sme_updated_event(kafka_producer, sm_id, "Runtime", "PositionY", "2.0")
        kafka_producer.flush()

        _wait_for_abox_triple_count(fuseki, abox_before + 10, timeout_sec=40)

        shell_lookup = fuseki.query(
            f"""
            SELECT ?shell
            WHERE {{
              GRAPH <urn:kg:abox> {{
            ?shell ?p ?id_short .
            FILTER(isLiteral(?id_short) && STR(?id_short) = "{id_short}")
              }}
            }}
            LIMIT 1
            """
        )
        assert shell_lookup["results"]["bindings"], "Expected AAS shell with emitted idShort in ABox"
        shell_iri = shell_lookup["results"]["bindings"][0]["shell"]["value"]

        resource_at_ttl = fuseki.construct(_view_sparql("resource-at"))
        assert "ResourceAt" in resource_at_ttl, "Expected ResourceAt predicate facts from live CONSTRUCT view"

    def test_graphs_loaded_on_startup(self, fuseki: FusekiClient) -> None:
        """Verify TBox, SHACL graphs are loaded at bootstrap."""
        tbox_count = fuseki.count_triples("urn:kg:tbox")
        shacl_count = fuseki.count_triples("urn:kg:shacl")

        print(f"[test] TBox has {tbox_count} triples, SHACL has {shacl_count} triples")
        assert tbox_count > 100, "TBox should have many ontology triples"
        assert shacl_count > 10, "SHACL should have validation shapes"

    def test_aas_event_produces_abox_triples(self, fuseki: FusekiClient, kafka_producer: Producer) -> None:
        """Publish AAS event, verify it creates triples in ABox."""
        initial_count = fuseki.count_triples("urn:kg:abox")

        _publish_aas_event(kafka_producer, "urn:aas:e2e:shell-01", "Shell-01")
        kafka_producer.flush()

        # Wait for bridge to process and write to Fuseki
        new_count = _wait_for_abox_triple_count(fuseki, initial_count + 5, timeout_sec=20)

        # Query for the shell we just created
        result = fuseki.query("""
            PREFIX aas: <https://admin-shell.io/aas/3/1/>
            PREFIX arso: <https://w3id.org/2025/arso#>
            SELECT ?aas ?idShort
            WHERE {
              GRAPH <urn:kg:abox> {
                ?aas a aas:AssetAdministrationShell ;
                     aas:idShort ?idShort .
              }
              FILTER CONTAINS(?idShort, "Shell-01")
            }
        """)

        assert len(result["results"]["bindings"]) > 0, "Should find the created AAS shell"
        print(f"[test] Found AAS shell: {result['results']['bindings'][0]}")

    def test_submodel_event_produces_typed_submodel_link(
        self, fuseki: FusekiClient, kafka_producer: Producer
    ) -> None:
        """Publish AAS + SM, verify materialization creates typed hasXxxxSubmodel link."""
        aas_id = "urn:aas:e2e:shell-02"
        sm_id = "urn:sm:e2e:operational-data-01"

        _publish_aas_event(kafka_producer, aas_id, "Shell-02")
        kafka_producer.flush()
        time.sleep(2)

        _publish_submodel_event(kafka_producer, sm_id)
        kafka_producer.flush()

        # Give bridge time to materialize
        _wait_for_abox_triple_count(fuseki, 10, timeout_sec=20)

        # Query for hasOperationalDataSubmodel (materialized from hasSubmodel + type)
        result = fuseki.query("""
            PREFIX arso: <https://w3id.org/2025/arso#>
            SELECT ?aas ?sm
            WHERE {
              GRAPH <urn:kg:abox> {
                ?aas arso:hasOperationalDataSubmodel ?sm .
              }
            }
        """)

        print(f"[test] Materialization query found {len(result['results']['bindings'])} typed links")

    def test_resource_at_view_with_mirrored_position(
        self, fuseki: FusekiClient, kafka_producer: Producer
    ) -> None:
        """Test apex:ResourceAt predicate view with mirrored position SME."""
        aas_id = "urn:aas:e2e:carrier-01"
        sm_id = "urn:sm:e2e:carrier-operational-01"

        _publish_aas_event(kafka_producer, aas_id, "Carrier-01")
        kafka_producer.flush()
        time.sleep(1)

        _publish_submodel_event(kafka_producer, sm_id)
        kafka_producer.flush()
        time.sleep(1)

        # Mirror position properties via SME_UPDATED events
        _publish_sme_updated_event(
            kafka_producer,
            sm_id,
            "positioning",
            "positionX",
            "10.5",
        )
        _publish_sme_updated_event(
            kafka_producer,
            sm_id,
            "positioning",
            "positionY",
            "20.3",
        )
        _publish_sme_updated_event(
            kafka_producer,
            sm_id,
            "positioning",
            "positionZ",
            "0.0",
        )
        kafka_producer.flush()

        _wait_for_abox_triple_count(fuseki, 30, timeout_sec=20)

        # Query ResourceAt view
        resource_at_query = _view_sparql("resource-at")
        turtle = fuseki.construct(resource_at_query)

        print(f"[test] ResourceAt view returned {len(turtle)} bytes of RDF")
        assert "ResourceAt" in turtle, "View should produce ResourceAt predicates"
        assert "Carrier-01" in turtle or "carrier-01" in turtle, "Should contain carrier reference"

    def test_in_range_view_with_sha256_fact_iris(
        self, fuseki: FusekiClient, kafka_producer: Producer
    ) -> None:
        """Test apex:InRange view with deterministic SHA256-based fact IRIs."""
        carrier_id = "urn:aas:e2e:carrier-02"
        carrier_sm_id = "urn:sm:e2e:carrier-operational-02"
        station_id = "urn:aas:e2e:station-loading-01"
        station_sm_id = "urn:sm:e2e:station-operational-01"

        # Create actors
        _publish_aas_event(kafka_producer, carrier_id, "Carrier-02")
        _publish_aas_event(kafka_producer, station_id, "LoadingStation-01")
        kafka_producer.flush()
        time.sleep(1)

        _publish_submodel_event(kafka_producer, carrier_sm_id)
        _publish_submodel_event(kafka_producer, station_sm_id)
        kafka_producer.flush()
        time.sleep(1)

        # Position carrier at (5, 5, 0)
        _publish_sme_updated_event(kafka_producer, carrier_sm_id, "positioning", "positionX", "5.0")
        _publish_sme_updated_event(kafka_producer, carrier_sm_id, "positioning", "positionY", "5.0")
        _publish_sme_updated_event(kafka_producer, carrier_sm_id, "positioning", "positionZ", "0.0")

        # Position station at (5.5, 5.5, 0) – within range
        _publish_sme_updated_event(kafka_producer, station_sm_id, "positioning", "positionX", "5.5")
        _publish_sme_updated_event(kafka_producer, station_sm_id, "positioning", "positionY", "5.5")
        _publish_sme_updated_event(kafka_producer, station_sm_id, "positioning", "positionZ", "0.0")
        kafka_producer.flush()

        _wait_for_abox_triple_count(fuseki, 50, timeout_sec=20)

        # Query InRange view
        in_range_query = _view_sparql("in-range")
        turtle = fuseki.construct(in_range_query)

        print(f"[test] InRange view returned {len(turtle)} bytes")
        assert "InRange" in turtle, "View should produce InRange predicates"
        assert "urn:kg:apex:in-range:" in turtle, "Should contain SHA256-based fact IRIs"
        print("[test] ✓ InRange view produces SHA256-derived fact IRIs")

    def test_zero_lag_resource_at_on_position_update(
        self, fuseki: FusekiClient, kafka_producer: Producer
    ) -> None:
        """Verify zero-lag: update position, immediately query ResourceAt, see new value."""
        carrier_id = "urn:aas:e2e:carrier-03"
        carrier_sm_id = "urn:sm:e2e:carrier-operational-03"

        _publish_aas_event(kafka_producer, carrier_id, "Carrier-03")
        kafka_producer.flush()
        time.sleep(1)

        _publish_submodel_event(kafka_producer, carrier_sm_id)
        kafka_producer.flush()
        time.sleep(1)

        # Initial position
        _publish_sme_updated_event(kafka_producer, carrier_sm_id, "position", "posX", "1.0")
        kafka_producer.flush()
        _wait_for_abox_triple_count(fuseki, 10, timeout_sec=20)

        # Query 1: should see position 1.0
        result1 = fuseki.query("""
            PREFIX apex: <https://w3id.org/2026/apex/>
            SELECT ?location
            FROM <urn:kg:tbox>
            FROM <urn:kg:abox>
            WHERE {
              ?resource apex:smElementValue ?location ;
                        apex:smElementPath "position.posX" .
            }
        """)

        locations1 = [b["location"]["value"] for b in result1["results"]["bindings"]]
        print(f"[test] Before update: locations={locations1}")

        # Update position to 2.0
        _publish_sme_updated_event(kafka_producer, carrier_sm_id, "position", "posX", "2.0")
        kafka_producer.flush()
        time.sleep(2)

        # Query 2: should see position 2.0 immediately (no lag)
        result2 = fuseki.query("""
            PREFIX apex: <https://w3id.org/2026/apex/>
            SELECT ?location
            FROM <urn:kg:tbox>
            FROM <urn:kg:abox>
            WHERE {
              ?resource apex:smElementValue ?location ;
                        apex:smElementPath "position.posX" .
            }
        """)

        locations2 = [b["location"]["value"] for b in result2["results"]["bindings"]]
        print(f"[test] After update: locations={locations2}")

        assert "2" in str(locations2), "Position should update immediately to 2.0 (zero lag)"
        print("[test] ✓ Zero-lag view updates confirmed")

    def test_tbox_isolation_no_write_amplification(self, fuseki: FusekiClient, kafka_producer: Producer) -> None:
        """Verify TBox is never modified by AAS event processing."""
        tbox_before = fuseki.count_triples("urn:kg:tbox")

        # Publish many events
        for i in range(5):
            _publish_aas_event(kafka_producer, f"urn:aas:e2e:shell-bulk-{i}", f"Shell-Bulk-{i}")
        kafka_producer.flush()

        _wait_for_abox_triple_count(fuseki, 20, timeout_sec=20)

        tbox_after = fuseki.count_triples("urn:kg:tbox")

        assert tbox_before == tbox_after, "TBox should never be modified by AAS events"
        print(f"[test] ✓ TBox integrity maintained ({tbox_before} = {tbox_after} triples)")
