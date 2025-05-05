# Clone and build:

```bash
    git clone git@github.com:tristan-schwoerer/planar-motors-experiments.git
    cd planar-motors-experiments
    git submodule update --init --recursive
```

# DevContainer
The DevContainer is configured such that it compiles and build all libraries needed for the development and building the project.
Open the project in VSCode
```bash
    cd planar-motors-experiments
    code .
```
Navigate to the devcontainer.json file in the .devcontainer folder.
Press Ctrl+Shift+P
Select `Dev Containers: Rebuild Container`

This installs all dependencies and opens the project as a devcontainer.


# Docker Compose
The Docker Compose file builds both of the dockerfiles below. It then can run the behaviour tree, and all stations.
```bash
    docker compose build
    docker compose up -d
```

# Build docker images
All Docker Images are built from the root of the repository
```bash
docker build --pull --rm -f 'BT_Controller/dockerfile' -t 'mqtt_bt_controller:latest' .
docker build --pull --rm -f 'PackML_Stations/dockerfile' -t 'mqtt_packml_stations:latest' .
```


