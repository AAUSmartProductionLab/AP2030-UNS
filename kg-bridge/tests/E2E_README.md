# End-to-End Test Suite: Real Stack Integration

This directory contains end-to-end tests for the full AAS → Kafka → kg-bridge → Fuseki pipeline.

## What's Tested

The `test_e2e_real_stack.py` test suite validates:

1. **Graph Initialization**: TBox, SHACL, and optional ABox seed graphs are loaded at bootstrap
2. **AAS Event Processing**: AAS and Submodel events from Kafka create triples in the ABox
3. **Materialization Rules**: Structural inferences (typed submodel links) are correctly materialized
4. **Dynamic Predicate Views**: All 5 CONSTRUCT views (`resource-at`, `product-at`, `occupied`, `operational`, `in-range`) execute correctly
5. **SHA256-Based Fact IRIs**: Deterministic fact identifiers are generated correctly in views
6. **Multi-Actor Spatial Reasoning**: InRange predicate correctly computes 3D distance between resources
7. **Zero-Lag Updates**: Position changes trigger immediate view updates without delay
8. **No Write Amplification**: TBox remains isolated from ABox writes; predicate views aren't materialized

## Test Classes and Fixtures

### Fixtures

- **`docker_stack`** (session scope): Starts docker-compose with Kafka, Fuseki, kg-bridge; tears down after session
- **`fuseki`** (function scope): FusekiClient for SPARQL queries
- **`kafka_producer`** (function scope): Kafka producer for publishing events

### Helper Classes

- **`FusekiClient`**: SPARQL query/update interface
  - `query(sparql)` → JSON-LD SELECT results
  - `construct(sparql)` → Turtle CONSTRUCT results  
  - `update(sparql_update)` → Execute INSERT/DELETE
  - `count_triples(graph)` → Count triples in named graph

### Test Class: `TestRealStackE2E`

| Test | Purpose |
|------|---------|
| `test_graphs_loaded_on_startup` | Verify TBox (~150 triples) and SHACL (~10+) loaded |
| `test_aas_event_produces_abox_triples` | Publish AAS, confirm ABox grows |
| `test_submodel_event_produces_typed_submodel_link` | Verify materialization creates typed hasXxxSubmodel |
| `test_resource_at_view_with_mirrored_position` | Query `resource-at` view with mirrored positions |
| `test_in_range_view_with_sha256_fact_iris` | Validate InRange produces SHA256-derived fact IRIs |
| `test_zero_lag_resource_at_on_position_update` | Confirm immediate view updates |
| `test_tbox_isolation_no_write_amplification` | TBox count unchanged after batch events |

## Prerequisites

- Docker + docker-compose
- Python 3.10+
- python requirements:
  - `requests>=2.32.3`
  - `confluent-kafka>=2.5`
  - `pytest>=7`
  - `rdflib>=7`

## Running the Tests

### Option 1: Pytest (Recommended, once pytest/ROS conflict resolved)

```bash
cd kg-bridge
pytest tests/test_e2e_real_stack.py -v -s
```

### Option 2: Direct Python Execution

```bash
cd kg-bridge
python3 << 'EOF'
import sys
sys.path.insert(0, '.')

from tests.test_e2e_real_stack import TestRealStackE2E, docker_stack, fuseki, kafka_producer
import pytest

# Run a single test
pytest.main([
    'tests/test_e2e_real_stack.py::TestRealStackE2E::test_graphs_loaded_on_startup',
    '-v', '-s'
])
EOF
```

### Option 3: Docker-Compose + Manual Query

```bash
# Start stack
docker compose -f docker-compose.yml --profile knowledge-graph up -d

# Wait for health checks
sleep 10

# Publish event via Kafka
echo '{"type":"AAS_CREATED","id":"urn:aas:test","aas":{"id":"urn:aas:test","idShort":"Test"}}' \
  | docker exec -i kg-kafka kafka-console-producer --broker-list localhost:9092 --topic aas-events

# Query Fuseki
curl -s -X POST -H "Content-Type: application/sparql-query" \
  -u admin:admin \
  --data 'SELECT ?s WHERE { GRAPH <urn:kg:abox> { ?s ?p ?o } }' \
  http://localhost:3030/kg/sparql

# Tear down
docker compose -f docker-compose.yml --profile knowledge-graph down
```

## Key Implementation Details

### Event Publishing

Events are published to Kafka topics `aas-events` and `submodel-events` with JSON payloads matching the AAS metamodel.

### Polling Strategy

Tests use `_wait_for_abox_triple_count()` to poll Fuseki until expected triples appear (with configurable timeout). This accounts for async Kafka delivery and bridge processing.

### View Execution

SPARQL CONSTRUCT views are executed via `/kg/sparql` endpoint using `FROM <urn:kg:tbox> FROM <urn:kg:abox>` (if present) to ensure access to both graphs.

### SHA256 Fact IRI Validation

In-range view fact IRIs use: `urn:kg:apex:in-range:{SHA256(resource|station)}` for deterministic identity. Tests confirm these IRIs appear in view output.

## Test Isolation & Cleanup

- **Session scope**: Docker stack persists for all tests in a session
- **Function scope**: Fuseki/Kafka state persists across tests (intentional, to avoid rebuild overhead)
- **Per-test isolation**: Tests use unique AAS/Submodel IDs (e.g., `urn:aas:e2e:shell-01`) to avoid collisions

## Debugging

### Check Fuseki State

```bash
curl -s -X POST -H 'Content-Type: application/sparql-query' \
  -u admin:admin \
  --data 'SELECT (COUNT(*) AS ?n) WHERE { GRAPH <urn:kg:abox> { ?s ?p ?o } }' \
  http://localhost:3030/kg/sparql
```

### Check Kafka Topics

```bash
docker exec kg-kafka kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic aas-events \
  --from-beginning \
  --max-messages 5
```

### View Bridge Logs

```bash
docker logs -f kg-bridge
```

## Future Improvements

1. **Pytest Integration**: Resolve ROS launch_testing plugin conflicts for native pytest integration
2. **CI/CD Hooks**: Integrate into GitHub Actions or GitLab CI
3. **Performance Profiling**: Measure latency from Kafka publish to Fuseki query
4. **Coverage Expansion**: Test deletion/retraction paths, multi-graph consistency
5. **Stability Hardening**: Retry logic for transient Fuseki/Kafka timeouts
