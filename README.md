# AP2030-UNS
# Clone and build:
```bash
    git clone git@github.com:AAUSmartProductionLab/AP2030-UNS.git
    cd AP2030-UNS
    git submodule update --init --recursive
```

# BT_Controller DevContainer
The DevContainer is configured such that it compiles and build all libraries needed for the development and building the project.
Open the project in VSCode
```bash
    cd planar-motors-experiments
    code .
```
Navigate to the devcontainer.json file in the .devcontainer folder.
Press Ctrl+Shift+P
Select `Dev Containers: Rebuild and Reopen in Container`

This installs all dependencies and opens the project as a devcontainer.

# Run
The stack can be run with the following command:
```bash
    sudo docker compose -f UNS-compose.yml up -d
```
This starts the following applications:
- HiveMQ Mqtt Broker
- Mqtt-Explorer
- TimescaleDB
- Grafana
- Portainer
- Configurator
- Groot2
- Behaviour Tree Controller
- PackML stations (simulated as python ndoes) 