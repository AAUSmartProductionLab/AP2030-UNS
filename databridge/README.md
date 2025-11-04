# BaSyx DataBridge Configuration

This directory contains the configuration files for Eclipse BaSyx DataBridge, which enables real-time data integration between MQTT topics and Asset Administration Shell (AAS) submodels.

## Configuration Files

### `aasserver.json`
Defines the AAS submodel endpoints and properties where data will be written.

**Current Configuration:**
- **Submodel**: Motor Operational Data (`urn:example:motor:submodel:operational-data:001`)
- **Properties**: CurrentSpeed, Temperature, Status

### `mqttconsumer.json`
Configures MQTT consumers that subscribe to topics and receive sensor data.

**Current Configuration:**
- **Broker**: HiveMQ (hivemq-broker:1883)
- **Topics**: 
  - `motor/currentspeed`
  - `motor/temperature`
  - `motor/status`
- **Authentication**: Anonymous (empty username/password)
- **Client IDs**: Unique per consumer

### `routes.json`
Maps MQTT data sources to AAS destinations through transformation pipelines.

**Current Configuration:**
- Direct passthrough (no transformers)
- Event-triggered updates

### `jsonatatransformer.json`
Defines JSONata transformations for data manipulation (currently empty).

## Data Flow

```
MQTT Topic (motor/currentspeed)
    ↓
MQTT Consumer (Motor_CurrentSpeed_sensor)
    ↓
Route (event trigger)
    ↓
AAS Property (Motor/CurrentSpeed)
```

## Testing

Publish a test message:
```bash
docker exec hivemq-broker /opt/hivemq/tools/mqtt-cli/bin/mqtt pub -h localhost -t motor/currentspeed -m '5000'
```

Verify in AAS:
```bash
curl -s "http://192.168.0.104:8081/submodels/dXJuOmV4YW1wbGU6bW90b3I6c3VibW9kZWw6b3BlcmF0aW9uYWwtZGF0YTowMDE=/submodel-elements/CurrentSpeed"
```

## Notes

- The databridge requires that AAS submodels exist before starting
- Each MQTT consumer must have a unique `clientId` for HiveMQ
- Empty `userName` and `password` fields enable anonymous MQTT authentication
