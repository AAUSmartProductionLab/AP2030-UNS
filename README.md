# AP2030-UNS
# Clone and build:
```bash
    git clone git@github.com:AAUSmartProductionLab/AP2030-UNS.git
    cd AP2030-UNS
    git submodule update --init --recursive
```

# Configuration

The Compose stacks in `compose/` run with built-in defaults. To reach the
services from other machines, set `EXTERNAL_HOST` to this machine's IP in a
`.env` file (e.g. `EXTERNAL_HOST=192.168.1.100`).

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
- `knowledge-graph`: Neo4j + Kafka Connect + Fuseki + kg-bridge (on the shared Kafka)

BaSyx publishes repository events to Kafka only (`kafka` service, always on);
the DMP and the knowledge-graph profile both consume them.

Optional knowledge graph settings:

```bash
KG_FUSEKI_ADMIN_PASSWORD=admin
KG_BRIDGE_TOPIC_PATTERN=aas-events.*
KG_BRIDGE_LOG_LEVEL=INFO
```

