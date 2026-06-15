# AGENTS.md

## Setup

```bash
cp .env.exampleOffice .env   # then edit EXTERNAL_HOST to your machine's IP
git submodule update --init --recursive
```

## Architecture

IIoT platform (IEC 63278 / AAS) orchestrating production stations via **MQTT** (Mosquitto broker, port 1883). Planning via PDDL+unified-planning. Knowledge graph via Kafka→Fuseki (optional), mirrored to GraphDB for visualization.

```
Configurator (React) ──→ MQTT ──→ Planner (Python) ──→ BT XML ──→ BT_Controller (C++)
                                          │                              │
                                          ▼                              ▼
                                   BaSyx AAS Env ←── Registration_Service ──→ MQTT ──→ Stations
                                          │
                                   Kafka ──→ kg-bridge ──→ Fuseki (RDF)
                                                         └─→ GraphDB (visualization)
```

- **BT_Controller** (C++20, CMake): loads Behavior Trees, calls AAS Operations via REST → MQTT delegation, publishes telemetry.
- **Planner** (Python): production planning pipeline (step0–7). Reads AAS data, builds PDDL, solves with Fast-Downward / Pyperplan / ENHSP, generates BT XML.
- **Registration_Service** (Python, port 8087): unified service for AAS registration + Operation Delegation (REST→MQTT bridge). Flask + Gunicorn.
- **kg-bridge** (Python): Kafka consumer → RDF projection → Fuseki; runs SPARQL materialization rules and CONSTRUCT views. Optionally mirrors writes to GraphDB (best-effort safety valve; in normal Docker operation both stay in sync).
- **Configurator** (React/Vite): drag-and-drop production layout editor. Dev on port 5173.
- **OperationDelegation/** is deprecated — functionality moved into Registration_Service.

## Docker Compose profiles

Core services (BaSyx, MQTT, BT_Controller, Registration_Service, DataBridge) start without any profile.

Profiles (set `COMPOSE_PROFILES` in `.env`, comma-separated):
- `simulated-stations` — Planner + simulated station processes
- `knowledge-graph` — Kafka + Fuseki + kg-bridge + GraphDB (visualization). Also requires `BASYX_FEATURE_KAFKA_ENABLED=true`, `SPRING_KAFKA_BOOTSTRAP_SERVERS=PLAINTEXT://kafka:9092`, `KAFKA_BOOTSTRAP_SERVERS=PLAINTEXT://kafka:9092`

Build and run:
```bash
docker compose build --parallel
docker compose up -d
```

`labServer-compose.yml` is a self-contained single-file variant (in-memory BaSyx, no MongoDB/Kafka).

## Tests

There is no root-level test runner. Each component is independent:

| Component | Command (run from repo root) |
|-----------|------|
| kg-bridge | `cd kg-bridge && pytest tests/ -v -p no:launch_testing` |
| kg-bridge E2E | `bash run_e2e_tests.sh` (starts full KG Docker stack) |
| Planner | `cd Planner && PYTHONPATH=.:third_party/unified-planning pytest tests/ -v` |
| Registration_Service | `pytest Registration_Service/tests/ -v` |
| BT_Controller | `cd BT_Controller/build && cmake .. -DBT_CONTROLLER_BUILD_TESTS=ON && make -j && ctest` |
| Configurator | `cd Configurator && npm run lint` (ESLint only, no unit test script) |

## Lint

Only one component has lint:
- `cd Configurator && npm run lint` (ESLint)

No mypy, no root-level tooling.

## Key gotchas

- **kg-bridge pytest needs ROS plugin disabled**: `-p no:launch_testing` (required; ROS launch_testing plugin conflicts with test collection). Already in `kg-bridge/pytest.ini`.
- **Planner needs custom unified-planning on PYTHONPATH**: The submodule at `Planner/third_party/unified-planning` (forked from upstream) must be on `PYTHONPATH` for tests and runtime.
- **`unified-planning/` at repo root is empty**; the actual code lives under `Planner/third_party/unified-planning/`.
- **BT_Controller config uses env var substitution**: `BT_Controller/config/controller_config.yaml` contains `${VAR:-default}` patterns expanded by the C++ binary at runtime, not by Docker.
- **DataBridge configs are auto-generated** from `AASDescriptions/` by Registration_Service. `databridge/*.json` and `databridge/queries/` are gitignored — do not commit them.
- **`aas/` is a runtime volume mount** for BaSyx (AAS .aasx/JSON files).
- **Env file is `.env`** (gitignored). Copy from `.env.exampleOffice`. Set `EXTERNAL_HOST` to your IP.
- **MongoDB is used by BaSyx** in the default compose. `labServer-compose.yml` uses in-memory backends instead.
- **No CI for tests** — only a GitHub Pages deploy workflow (`sync-schemas.yml`) that publishes schemas from `AASDescriptions/`, `MQTTSchemas/`, `BTDescriptions/`.
- **GraphDB visualization**: Access the Workbench at `http://<host>:7200`. GraphDB receives the same data as Fuseki (best-effort safety valve; in normal Docker operation both stay in sync). To force a clean rebuild (wipe GraphDB data and re-import from scratch): `docker compose up -d --force-recreate graphdb graphdb-bootstrap`.
- **GraphDB visualization**: Access the Workbench at `http://<host>:7200`. GraphDB receives the same data as Fuseki (best-effort safety valve; in normal Docker operation both stay in sync). To force a clean rebuild (wipe GraphDB data and re-import from scratch): `docker compose up -d --force-recreate graphdb graphdb-bootstrap`.
- **Head-to-head evaluation**: The `test_graphdb_head_to_head` E2E test compares both backends — triple counts, graph isomorphism, and query timing — and prints a comparison table. Set `PRIMARY_UPDATE_URL` and `PRIMARY_QUERY_URL` in `.env` to test GraphDB as the primary backend. Note: GraphDB Free (the Docker image) has Full SPARQL 1.1 support including SPARQL Update; writes go to `/repositories/{id}/statements`.
