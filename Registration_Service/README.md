# BaSyx AAS Registration Service

Automated registration service for Asset Administration Shells (AAS) and Submodels with Eclipse BaSyx, including DataBridge configuration generation and automatic MQTT topic mapping.

## Features

- 📦 **AASX File Registration**: Parse and register AAS from AASX packages
- 📄 **JSON-based Registration**: Register AAS with custom MQTT topic mappings from JSON files
- 🔄 **Automatic DataBridge Configuration**: Generates complete DataBridge configs (MQTT, AAS, Routes)
- 🔗 **Custom Topic Mapping**: Map any MQTT topic structure to AAS properties
- 🚀 **Auto-restart**: Automatically restarts DataBridge container after registration
- 📋 **Registry Integration**: Posts to both AAS Shell Registry (port 8082) and Submodel Registry (port 8083)

## Prerequisites

- Python 3.8+
- Docker (for DataBridge container restart)
- Eclipse BaSyx 2.0.0-SNAPSHOT running
  - AAS Environment: http://192.168.0.104:8081
  - AAS Shell Registry: http://192.168.0.104:8082
  - Submodel Registry: http://192.168.0.104:8083
- HiveMQ MQTT Broker: hivemq-broker:1883

## Installation

No installation required - standalone Python script with standard library dependencies only.

```bash
cd Registration_Service
python3 aas-registration-service.py --help
```

## Usage

### 1. Register from AASX File

Register an existing AASX file with auto-generated MQTT topics:

```bash
python3 aas-registration-service.py register path/to/file.aasx [--mqtt-broker hivemq-broker] [--basyx-url http://192.168.0.104:8081]
```

**Example:**
```bash
python3 aas-registration-service.py register ../aas/example-motor-fixed.aasx
```

**Auto-generated topics:**
- Pattern: `{submodel_idShort}/{property_idShort}`
- Example: `motor/currentspeed`, `motor/temperature`

### 2. Register from JSON with Custom Topics (Recommended)

Register AAS with explicit MQTT topic mappings for flexible integration:

```bash
python3 aas-registration-service.py register-json path/to/registration.json [--mqtt-broker hivemq-broker] [--basyx-url http://192.168.0.104:8081]
```

**Example:**
```bash
python3 aas-registration-service.py register-json robot_registration.json
```

**What it does:**
1. ✅ Parses JSON file with AAS data and topic_mappings
2. ✅ Registers all submodels in AAS repository
3. ✅ Registers submodel descriptors in Submodel Registry
4. ✅ Registers shell descriptor in AAS Shell Registry
5. ✅ Generates DataBridge configurations with custom topics
6. ✅ Automatically restarts DataBridge container

### 3. Configure DataBridge Settings

Update MQTT broker settings in existing configurations:

```bash
python3 aas-registration-service.py configure --mqtt-broker <hostname> [--mqtt-port 1883]
```

### 4. List Registered AAS

View all registered AAS shells and submodels:

```bash
python3 aas-registration-service.py list [--basyx-url http://192.168.0.104:8081]
```

## JSON Registration Format

The JSON format allows you to define both AAS structure and custom MQTT topic mappings in a single file.

### Structure

```json
{
  "aas_data": {
    "assetAdministrationShells": [...],
    "submodels": [...]
  },
  "topic_mappings": {
    "mqtt/topic/path": "SubmodelIdShort/PropertyIdShort"
  }
}
```

### Complete Example: Industrial Robot

See `robot_registration.json` for a full example with:
- 1 AAS Shell (`IndustrialRobot`)
- 3 Submodels (`Motion`, `Safety`, `Tooling`)
- 10 Properties with custom factory/* topics

**Topic Mappings:**
```json
{
  "factory/line3/robot/position/x": "Motion/XPosition",
  "factory/line3/robot/position/y": "Motion/YPosition",
  "factory/line3/robot/position/z": "Motion/ZPosition",
  "factory/line3/robot/motion/speed": "Motion/Speed",
  "factory/line3/robot/safety/emergency_stop": "Safety/EmergencyStop",
  "factory/line3/robot/safety/door": "Safety/DoorOpen",
  "factory/line3/robot/safety/error": "Safety/ErrorCode",
  "factory/line3/robot/tool/gripper_state": "Tooling/GripperState",
  "factory/line3/robot/tool/id": "Tooling/ToolId",
  "factory/line3/robot/tool/pressure": "Tooling/Pressure"
}
```

### AAS Data Format

The `aas_data` section follows the AAS Metamodel v3 JSON structure:

**Asset Administration Shell:**
```json
{
  "idShort": "IndustrialRobot",
  "id": "urn:example:robot:aas:001",
  "assetInformation": {
    "assetKind": "Instance",
    "globalAssetId": "urn:example:robot:asset:001"
  },
  "submodels": [
    {
      "type": "ExternalReference",
      "keys": [{"type": "Submodel", "value": "urn:example:robot:submodel:motion:001"}]
    }
  ]
}
```

**Submodel:**
```json
{
  "idShort": "Motion",
  "id": "urn:example:robot:submodel:motion:001",
  "semanticId": {
    "type": "ExternalReference",
    "keys": [{"type": "GlobalReference", "value": "https://example.com/ids/cd/Motion"}]
  },
  "submodelElements": [
    {
      "idShort": "XPosition",
      "modelType": "Property",
      "valueType": "xs:double",
      "value": "0.0"
    }
  ]
}
```

## Generated DataBridge Configuration

The service automatically generates four configuration files in `../databridge/`:

### 1. mqttconsumer.json
MQTT consumer configurations with custom topics:

```json
[
  {
    "uniqueId": "Motion_XPosition_sensor",
    "serverUrl": "hivemq-broker",
    "serverPort": 1883,
    "topic": "factory/line3/robot/position/x"
  }
]
```

**Note**: Optional fields like `clientId`, `userName`, and `password` are omitted:
- **clientId**: Auto-generated by the MQTT client if not specified
- **userName/password**: Not needed for anonymous MQTT authentication

Add these fields only if your broker requires authentication or you need specific client IDs.

### 2. aasserver.json
AAS endpoint mappings:

```json
[
  {
    "uniqueId": "Motion_XPosition_aas",
    "submodelEndpoint": "http://aas-env:8081/submodels/dXJu...==",
    "idShortPath": "XPosition"
  }
]
```

### 3. routes.json
Data flow routing from MQTT to AAS:

```json
[
  {
    "routeId": "Motion_XPosition_route",
    "datasource": "Motion_XPosition_sensor",
    "transformers": [],
    "datasinks": ["Motion_XPosition_aas"],
    "trigger": "event"
  }
]
```

### 4. jsonatatransformer.json
Data transformations (empty if not needed):

```json
[]
```

## Testing the Integration

### 1. Verify Registration

Check that the shell was registered:
```bash
curl http://192.168.0.104:8082/shell-descriptors | python3 -m json.tool
```

Check submodels:
```bash
curl http://192.168.0.104:8083/submodel-descriptors | python3 -m json.tool
```

### 2. Check DataBridge Status

View DataBridge logs:
```bash
docker logs databridge --tail 50
```

You should see routes started:
```
[main] INFO - Started route1 (paho://factory/line3/robot/position/x)
[main] INFO - Started route2 (paho://factory/line3/robot/position/y)
...
```

### 3. Test MQTT → AAS Data Flow

Publish a test message:
```bash
docker exec hivemq-broker /opt/hivemq/tools/mqtt-cli/bin/mqtt pub \
  -h localhost \
  -t "factory/line3/robot/position/x" \
  -m "125.5"
```

Verify the value in AAS:
```bash
curl -s "http://192.168.0.104:8081/submodels/$(echo -n 'urn:example:robot:submodel:motion:001' | base64 -w 0)/submodel-elements/XPosition" | python3 -m json.tool
```

Expected output:
```json
{
  "modelType": "Property",
  "value": "125.5",
  "valueType": "xs:double",
  "idShort": "XPosition"
}
```

### 4. Monitor Live Updates

Subscribe to all factory topics:
```bash
docker exec hivemq-broker /opt/hivemq/tools/mqtt-cli/bin/mqtt sub \
  -h localhost \
  -t "factory/line3/robot/#" \
  -v
```

Publish from another terminal and watch updates.

## Architecture

```
┌─────────────┐     MQTT Topics           ┌──────────────┐
│   Sensors   │────────────────────────────>│  HiveMQ      │
│  (External) │  factory/line3/robot/*     │   Broker     │
└─────────────┘                            └──────┬───────┘
                                                  │
                                                  │ Subscribe
                                                  ▼
                                           ┌──────────────┐
                                           │  DataBridge  │
                                           │  - Consumer  │
                                           │  - Routes    │
                                           │  - Producers │
                                           └──────┬───────┘
                                                  │
                                                  │ HTTP PUT
                                                  ▼
┌──────────────────────────────────────────────────────────┐
│              Eclipse BaSyx Platform                      │
│                                                          │
│  ┌────────────────┐  ┌─────────────────┐               │
│  │ AAS Environment│  │  Shell Registry │               │
│  │   (port 8081)  │  │   (port 8082)   │               │
│  └────────────────┘  └─────────────────┘               │
│                                                          │
│  ┌─────────────────┐                                    │
│  │ Submodel Registry│                                   │
│  │   (port 8083)    │                                   │
│  └─────────────────┘                                    │
└──────────────────────────────────────────────────────────┘
```

## Benefits of JSON Registration

### Flexible Topic Hierarchies
- Support existing MQTT topic structures
- Organize by factory, line, cell, equipment
- No need to change sensor configurations

### Example Use Cases

**Smart Factory:**
```
factory/line1/cell2/robot/status → Cell2/Robot/Status
factory/line1/cell2/conveyor/speed → Cell2/Conveyor/Speed
```

**Building Automation:**
```
building/floor3/room301/temp → Floor3/Room301/Temperature
building/floor3/room301/co2 → Floor3/Room301/CO2Level
```

**Vehicle Fleet:**
```
fleet/truck42/gps/lat → Truck42/Location/Latitude
fleet/truck42/gps/lon → Truck42/Location/Longitude
fleet/truck42/fuel → Truck42/Status/FuelLevel
```

## Troubleshooting

### DataBridge Not Connecting

1. Check broker connectivity:
   ```bash
   docker exec databridge ping hivemq-broker
   ```

2. Verify MQTT credentials in `mqttconsumer.json`

3. Check HiveMQ logs:
   ```bash
   docker logs hivemq-broker --tail 100
   ```

### AAS Submodels Not Found

1. Verify submodels are registered:
   ```bash
   curl http://192.168.0.104:8081/submodels | python3 -m json.tool
   ```

2. Check submodel IDs match in `aasserver.json`

3. DataBridge validates submodels exist before starting routes

### Property Not Updating

1. Check DataBridge logs for errors:
   ```bash
   docker logs databridge --tail 100 | grep ERROR
   ```

2. Verify property path is correct: `SubmodelIdShort/PropertyIdShort`

3. Ensure MQTT topic matches `topic_mappings` in JSON

### Docker Restart Fails

If automatic restart fails, manually restart:
```bash
docker restart databridge
```

Check Docker daemon is running:
```bash
systemctl status docker
```

## Advanced Configuration

### Custom BaSyx URL

For different BaSyx deployments:
```bash
python3 aas-registration-service.py register-json robot.json \
  --basyx-url http://custom-host:8081
```

### Custom MQTT Broker

For different MQTT brokers:
```bash
python3 aas-registration-service.py register-json robot.json \
  --mqtt-broker mqtt.example.com
```

### Multiple Environments

Use different JSON files per environment:
- `production_robot.json` - Production MQTT topics
- `staging_robot.json` - Staging topics
- `dev_robot.json` - Development topics

## Files

- `aas-registration-service.py` - Main registration service script
- `robot_registration.json` - Example JSON registration file
- `README.md` - This documentation

## Related Documentation

- [BaSyx DataBridge Documentation](https://github.com/eclipse-basyx/basyx-databridge)
- [AAS Metamodel v3](https://industrialdigitaltwin.org/en/content-hub/aasspecifications)
- [Eclipse BaSyx](https://eclipse-basyx.github.io/)
- [HiveMQ Documentation](https://www.hivemq.com/docs/)

## License

See workspace root LICENSE file.

## Support

For issues related to:
- **BaSyx**: Eclipse BaSyx GitHub Issues
- **DataBridge**: Eclipse BaSyx DataBridge GitHub
- **This Tool**: Contact project maintainer
