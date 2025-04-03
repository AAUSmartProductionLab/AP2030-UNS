# DevContainer
The DevContainer is configured based on the other dockerfiles, such that it compiles and build all libraries correctly and allows development on both, the python and the c++ parts

# Docker Compose
The Docker Compose file builds both of the dockerfiles below. It then can run the behaviour tree, and all stations.
```bash
    docker compose build
    docker compose up -d
```

# Build docker images
All Docker Images are built from the root of the repository
```bash
docker build --pull --rm -f 'MQTT_BT_Controller/dockerfile' -t 'mqtt_bt_controller:latest' .
docker build --pull --rm -f 'MQTT_PackML_Stations/dockerfile' -t 'mqtt_packml_stations:latest' .
```


