# AP2030-UNS
# Clone and build:
```bash
    git clone git@github.com:AAUSmartProductionLab/AP2030-UNS.git
    cd AP2030-UNS
    git submodule update --init --recursive
```

# Configuration

Before running the system, configure your environment:

```bash
    # Copy the example environment file
    cp .env.exampleOffice .env
    
    # Edit .env and set your machine's IP address
    # Update EXTERNAL_HOST to your machine's IP (e.g., 192.168.1.100)
    nano .env
```

For detailed configuration instructions, see [CONFIGURATION.md](CONFIGURATION.md).

# Schemas and AAS Templates

All json schemas are hosted on github pages under the following link:
https://aausmartproductionlab.github.io/AP2030-UNS/


# BT_Controller DevContainer
The DevContainer is configured such that it compiles and build all libraries needed for the development and building the project.
Open the project in VSCode
```bash
    cd AP2030
    code .
```
Navigate to the devcontainer.json file in the .devcontainer folder.
Press Ctrl+Shift+P
Select `Dev Containers: Rebuild and Reopen in Container`

This installs all dependencies and opens the project as a devcontainer.

# Run
The stack can be first build and then run with the following commands:
```bash
    cd AP2030
    docker compose build --parallel
    docker compose up -d
```

## Module Flags via .env

Use `COMPOSE_PROFILES` in `.env` to control optional modules while still running with plain `docker compose up`.

Example:

```bash
COMPOSE_PROFILES=simulated-stations,knowledge-graph
```

Available profile modules:
- `simulated-stations`: production planner + simulated station services
- `knowledge-graph`: Kafka + Neo4j + Kafka Connect + Fuseki + kg-bridge

Knowledge graph profile also requires Kafka eventing variables in `.env`:

```bash
BASYX_FEATURE_KAFKA_ENABLED=true
SPRING_KAFKA_BOOTSTRAP_SERVERS=PLAINTEXT://kafka:9092
KAFKA_BOOTSTRAP_SERVERS=PLAINTEXT://kafka:9092
```

Optional knowledge graph settings:

```bash
KG_FUSEKI_ADMIN_PASSWORD=admin
KG_BRIDGE_TOPIC_PATTERN=aas-events.*
KG_BRIDGE_LOG_LEVEL=INFO
```

One-time migration when switching to the live py-aas-rdf mapping:

```bash
./kg-bridge/migrate.sh
```

This drops the ABox graph (`KG_ABOX_GRAPH`, default `urn:kg:abox`) in Fuseki so
it can be rebuilt cleanly with the new canonical IRIs and predicates. TBox and
SHACL graphs are not dropped.

If you disable `knowledge-graph`, set those values back to defaults:

```bash
BASYX_FEATURE_KAFKA_ENABLED=false
SPRING_KAFKA_BOOTSTRAP_SERVERS=
KAFKA_BOOTSTRAP_SERVERS=
```
