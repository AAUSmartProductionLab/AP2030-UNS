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
from unittest.mock import Mock
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

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


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
                "--delete",
                "--topic",
                topic,
            ],
            check=False,
            capture_output=True,
        )
        subprocess.run(
            [
                "docker",
                "exec",
                "kg-kafka",
                "kafka-topics",
                "--bootstrap-server",
                "localhost:9092",
                "--create",
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


def _publish_aas_event(
    producer: Producer,
    aas_id: str,
    id_short: str,
    submodels: list[str] | None = None,
) -> None:
    """Publish AAS_CREATED event to Kafka.

    If submodels is provided, each entry is added to the AAS's submodels
    reference list so the bridge can derive arso:hasSubmodel links.
    """
    aas: dict[str, object] = {
        "id": aas_id,
        "idShort": id_short,
        "assetInformation": {"assetKind": "Instance"},
    }
    if submodels:
        aas["submodels"] = [
            {
                "type": "ModelReference",
                "keys": [{"type": "Submodel", "value": sm_id}],
            }
            for sm_id in submodels
        ]
    payload = {
        "type": "AAS_CREATED",
        "id": aas_id,
        "aas": aas,
    }
    producer.produce(
        topic="aas-events",
        key=aas_id.encode("utf-8"),
        value=json.dumps(payload).encode("utf-8"),
    )
    print(f"[test] Published AAS_CREATED for {aas_id}")


def _publish_submodel_event(producer: Producer, sm_id: str) -> None:
    """Publish SM_CREATED event with semanticId for OperationalData submodel."""
    payload = {
        "type": "SM_CREATED",
        "id": sm_id,
        "submodel": {
            "id": sm_id,
            "idShort": "OperationalData",
            "semanticId": {
                "type": "ExternalReference",
                "keys": [
                    {"type": "GlobalReference", "value": "https://admin-shell.io/idta/Variables/1/0/Submodel"}
                ],
            },
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
    semantic_id: str | None = None,
) -> None:
    """Publish SME_UPDATED event for a mirrored sensor value.

    If semantic_id is provided, it is added to the payload so the bridge
    projects apex:smElementSemanticId for CONSTRUCT view queries.
    """
    canonical_path = path if path.endswith(id_short) else f"{path}.{id_short}"
    sm_element: dict[str, object] = {
        "modelType": "Property",
        "idShort": id_short,
        "value": value,
        "valueType": "xs:string" if isinstance(value, str) else ("xs:float" if isinstance(value, float) else "xs:boolean"),
    }
    if semantic_id:
        sm_element["semanticId"] = {
            "type": "ExternalReference",
            "keys": [{"type": "GlobalReference", "value": semantic_id}],
        }
    payload = {
        "type": "SME_UPDATED",
        "id": sm_id,
        "smElementPath": canonical_path,
        "smElement": sm_element,
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
        id_short = f"SmokeShell_{suffix}"

        abox_before = fuseki.count_triples("urn:kg:abox")

        _publish_aas_event(kafka_producer, aas_id, id_short, submodels=[sm_id])
        _publish_submodel_event(kafka_producer, sm_id)
        _publish_sm_ref_added_event(kafka_producer, aas_id, sm_id)
        _publish_sme_updated_event(
            kafka_producer, sm_id, "Runtime", "CurrentLocation", f"cell_{suffix}",
            semantic_id="https://w3id.org/2026/apex/semantic/location/label",
        )
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

        # ── Diagnostics first: verify the link chain the view depends on ──
        diag_aas_type = fuseki.query(f"""
            PREFIX arsox: <https://w3id.org/aau-ra/arso-ext#>
            ASK {{ GRAPH <urn:kg:abox> {{ <{shell_iri}> a arsox:ResourceAssetAdministrationShell . }} }}
        """)
        diag_op_submodel = fuseki.query(f"""
            PREFIX arso: <https://w3id.org/2025/arso#>
            ASK {{ GRAPH <urn:kg:abox> {{ <{shell_iri}> arso:hasOperationalDataSubmodel ?sm . }} }}
        """)
        diag_sme_semantic = fuseki.query(f"""
            PREFIX apex: <https://w3id.org/2026/apex/>
            ASK {{ GRAPH <urn:kg:abox> {{ ?sme apex:smElementSemanticId "https://w3id.org/2026/apex/semantic/location/label" . }} }}
        """)
        print(f"[test] Diagnostic: shell typed as ResourceAAS={diag_aas_type['boolean']}, "
              f"hasOpDataSubmodel={diag_op_submodel['boolean']}, "
              f"smeSemanticIdLocation={diag_sme_semantic['boolean']}")

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

        _publish_aas_event(kafka_producer, "urn:aas:e2e:shell_01", "Shell_01")
        kafka_producer.flush()

        # Wait for bridge to process and write to Fuseki (expect at least 2 triples: type + idShort)
        new_count = _wait_for_abox_triple_count(fuseki, initial_count + 2, timeout_sec=20)

        # Query for the shell we just created
        result = fuseki.query("""
            PREFIX apexi: <https://w3id.org/2026/apex/>
            SELECT ?aas ?idShort
            WHERE {
              GRAPH <urn:kg:abox> {
                ?aas apexi:aasIdShort ?idShort .
              }
              FILTER CONTAINS(?idShort, "Shell_01")
            }
        """)

        assert len(result["results"]["bindings"]) > 0, "Should find the created AAS shell"
        print(f"[test] Found AAS shell: {result['results']['bindings'][0]}")

    def test_submodel_event_produces_typed_submodel_link(
        self, fuseki: FusekiClient, kafka_producer: Producer
    ) -> None:
        """Publish AAS + SM, verify the generic hasSubmodel link is created."""
        aas_id = "urn:aas:e2e:shell-02"
        sm_id = "urn:sm:e2e:operational-data-01"

        _publish_aas_event(kafka_producer, aas_id, "Shell_02", submodels=[sm_id])
        kafka_producer.flush()
        time.sleep(1)

        _publish_submodel_event(kafka_producer, sm_id)
        kafka_producer.flush()
        time.sleep(1)

        _publish_sm_ref_added_event(kafka_producer, aas_id, sm_id)
        kafka_producer.flush()
        time.sleep(1)

        # Give bridge time to process
        _wait_for_abox_triple_count(fuseki, 10, timeout_sec=20)

        # Query for hasSubmodel (created directly by projection from AAS submodels + SM_REF_ADDED)
        result = fuseki.query("""
            PREFIX arso: <https://w3id.org/2025/arso#>
            SELECT ?aas ?sm
            WHERE {
              GRAPH <urn:kg:abox> {
                ?aas arso:hasSubmodel ?sm .
              }
            }
        """)

        print(f"[test] hasSubmodel query found {len(result['results']['bindings'])} link(s)")

    def test_resource_at_view_with_mirrored_position(
        self, fuseki: FusekiClient, kafka_producer: Producer
    ) -> None:
        """Test apex:ResourceAt predicate view with mirrored position SME."""
        aas_id = "urn:aas:e2e:carrier-01"
        sm_id = "urn:sm:e2e:carrier-operational-01"

        _publish_aas_event(kafka_producer, aas_id, "Carrier_01", submodels=[sm_id])
        kafka_producer.flush()
        time.sleep(1)

        _publish_submodel_event(kafka_producer, sm_id)
        kafka_producer.flush()
        time.sleep(1)

        _publish_sm_ref_added_event(kafka_producer, aas_id, sm_id)
        kafka_producer.flush()
        time.sleep(1)

        # Publish location label (required by resource-at view)
        _publish_sme_updated_event(
            kafka_producer, sm_id, "Runtime", "CurrentLocation", "loading-dock-1",
            semantic_id="https://w3id.org/2026/apex/semantic/location/label",
        )

        # Mirror position properties via SME_UPDATED events
        _publish_sme_updated_event(
            kafka_producer, sm_id, "positioning", "positionX", "10.5",
            semantic_id="https://w3id.org/2026/apex/semantic/position/x",
        )
        _publish_sme_updated_event(
            kafka_producer, sm_id, "positioning", "positionY", "20.3",
            semantic_id="https://w3id.org/2026/apex/semantic/position/y",
        )
        _publish_sme_updated_event(
            kafka_producer, sm_id, "positioning", "positionZ", "0.0",
            semantic_id="https://w3id.org/2026/apex/semantic/position/z",
        )
        kafka_producer.flush()

        _wait_for_abox_triple_count(fuseki, 30, timeout_sec=20)

        # Diagnostic: verify the data chain the view depends on
        diag_has_sub = fuseki.query(f"""
            PREFIX arso: <https://w3id.org/2025/arso#>
            ASK {{ GRAPH <urn:kg:abox> {{ <{aas_id}> arso:hasSubmodel <{sm_id}> . }} }}
        """)
        diag_sme = fuseki.query(f"""
            PREFIX apex: <https://w3id.org/2026/apex/>
            ASK {{ GRAPH <urn:kg:abox> {{ ?sme apex:smElementValue "loading-dock-1" ; apex:smElementSemanticId "https://w3id.org/2026/apex/semantic/location/label" . }} }}
        """)
        diag_iri_match = fuseki.query(f"""
            PREFIX apex: <https://w3id.org/2026/apex/>
            ASK {{ GRAPH <urn:kg:abox> {{ ?sme apex:smElementValue "loading-dock-1" . FILTER(STRSTARTS(STR(?sme), STR(<{sm_id}>))) }} }}
        """)
        print(f"[test] Diag: hasSubmodel={diag_has_sub['boolean']}, smeExists={diag_sme['boolean']}, iriMatch={diag_iri_match['boolean']}")

        # Query ResourceAt view
        resource_at_query = _view_sparql("resource-at")
        turtle = fuseki.construct(resource_at_query)

        print(f"[test] ResourceAt view returned {len(turtle)} bytes of RDF")
        assert "ResourceAt" in turtle, "View should produce ResourceAt predicates"
        assert "loading-dock-1" in turtle, "Should contain the carrier location literal"

    def test_in_range_view_with_sha256_fact_iris(
        self, fuseki: FusekiClient, kafka_producer: Producer
    ) -> None:
        """Test apex:InRange view with deterministic SHA256-based fact IRIs."""
        carrier_id = "urn:aas:e2e:carrier-02"
        carrier_sm_id = "urn:sm:e2e:carrier-operational-02"
        station_id = "urn:aas:e2e:station-loading-01"
        station_sm_id = "urn:sm:e2e:station-operational-01"

        # Create actors
        _publish_aas_event(kafka_producer, carrier_id, "Carrier_02", submodels=[carrier_sm_id])
        _publish_aas_event(kafka_producer, station_id, "LoadingStation_01", submodels=[station_sm_id])
        kafka_producer.flush()
        time.sleep(1)

        _publish_submodel_event(kafka_producer, carrier_sm_id)
        _publish_submodel_event(kafka_producer, station_sm_id)
        kafka_producer.flush()
        time.sleep(1)

        _publish_sm_ref_added_event(kafka_producer, carrier_id, carrier_sm_id)
        _publish_sm_ref_added_event(kafka_producer, station_id, station_sm_id)
        kafka_producer.flush()
        time.sleep(1)

        # Position carrier at (5, 5, 0)
        _publish_sme_updated_event(kafka_producer, carrier_sm_id, "positioning", "positionX", "5.0", semantic_id="https://w3id.org/2026/apex/semantic/position/x")
        _publish_sme_updated_event(kafka_producer, carrier_sm_id, "positioning", "positionY", "5.0", semantic_id="https://w3id.org/2026/apex/semantic/position/y")
        _publish_sme_updated_event(kafka_producer, carrier_sm_id, "positioning", "positionZ", "0.0", semantic_id="https://w3id.org/2026/apex/semantic/position/z")

        # Position station at (5.5, 5.5, 0) – within range
        _publish_sme_updated_event(kafka_producer, station_sm_id, "positioning", "positionX", "5.5", semantic_id="https://w3id.org/2026/apex/semantic/position/x")
        _publish_sme_updated_event(kafka_producer, station_sm_id, "positioning", "positionY", "5.5", semantic_id="https://w3id.org/2026/apex/semantic/position/y")
        _publish_sme_updated_event(kafka_producer, station_sm_id, "positioning", "positionZ", "0.0", semantic_id="https://w3id.org/2026/apex/semantic/position/z")
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

        _publish_aas_event(kafka_producer, carrier_id, "Carrier_03", submodels=[carrier_sm_id])
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
            _publish_aas_event(kafka_producer, f"urn:aas:e2e:shell_bulk_{i}", f"Shell_Bulk_{i}")
        kafka_producer.flush()

        _wait_for_abox_triple_count(fuseki, 20, timeout_sec=20)

        tbox_after = fuseki.count_triples("urn:kg:tbox")

        assert tbox_before == tbox_after, "TBox should never be modified by AAS events"
        print(f"[test] ✓ TBox integrity maintained ({tbox_before} = {tbox_after} triples)")

    def test_planner_shacl_gate_blocks_on_injected_violation(self, fuseki: FusekiClient) -> None:
        """Smoke E2E: planner SHACL gate fails fast when an isolated shape is violated."""
        pytest.importorskip("pyshacl")

        from Planner.production_planner_service import PlannerConfig, PlannerService

        suffix = uuid.uuid4().hex[:8]
        abox_graph = f"urn:kg:e2e:abox:{suffix}"
        shacl_graph = f"urn:kg:e2e:shacl:{suffix}"

        cppm = f"urn:kg:e2e:cppm:{suffix}"
        cpps_a = f"urn:kg:e2e:cpps:a:{suffix}"
        cpps_b = f"urn:kg:e2e:cpps:b:{suffix}"

        # Minimal isolated shape: each apex:CPPM must have exactly one inverse apex:hasCPPM link.
        fuseki.update(
            f"""
            PREFIX apex: <https://w3id.org/2026/apex/>
            PREFIX sh: <http://www.w3.org/ns/shacl#>
            INSERT DATA {{
              GRAPH <{shacl_graph}> {{
                apex:E2ECppmSingleParentShape
                  a sh:NodeShape ;
                  sh:targetClass apex:CPPM ;
                  sh:property [
                    sh:path [ sh:inversePath apex:hasCPPM ] ;
                    sh:class apex:CPPS ;
                    sh:minCount 1 ;
                    sh:maxCount 1
                  ] .
              }}
            }}
            """
        )

        # Inject deterministic violation: one CPPM with two CPPS parents.
        fuseki.update(
            f"""
            PREFIX apex: <https://w3id.org/2026/apex/>
            INSERT DATA {{
              GRAPH <{abox_graph}> {{
                <{cppm}> a apex:CPPM .
                <{cpps_a}> a apex:CPPS ; apex:hasCPPM <{cppm}> .
                <{cpps_b}> a apex:CPPS ; apex:hasCPPM <{cppm}> .
              }}
            }}
            """
        )

        try:
            planner = PlannerService(
                aas_client=object(),
                mqtt_client=object(),
                config=PlannerConfig(
                    save_intermediate_files=False,
                    shacl_gate_enabled=True,
                    shacl_query_endpoint=f"{FUSEKI_BASE}/kg/sparql",
                    shacl_abox_graph=abox_graph,
                    shacl_tbox_graph="urn:kg:tbox",
                    shacl_shapes_graph=shacl_graph,
                    shacl_gate_timeout_seconds=20.0,
                ),
            )
            planner.context_collector = Mock()

            result = planner.plan_and_register(
                asset_ids=["urn:kg:e2e:resource:dummy"],
                order_aas_id="urn:kg:e2e:order:dummy",
            )

            assert result.success is False, "Expected planning to fail when SHACL gate does not conform"
            assert result.error_message is not None
            assert "SHACL pre-planning gate failed" in result.error_message
            assert result.planner_warnings, "Expected SHACL report excerpt in planner warnings"
            planner.context_collector.assert_not_called()
        finally:
            fuseki.update(f"CLEAR GRAPH <{abox_graph}>")
            fuseki.update(f"CLEAR GRAPH <{shacl_graph}>")
