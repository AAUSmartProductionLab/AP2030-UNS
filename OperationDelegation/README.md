# Operation Delegation Service

This service bridges BaSyx AAS Operations with MQTT-controlled assets. When an AAS Operation is invoked through BaSyx, this service translates the operation into MQTT commands and waits for responses.

## Overview

The Operation Delegation Service implements the [BaSyx Operation Delegation pattern](https://wiki.basyx.org/en/latest/content/concepts/use_cases/aas_operations.html):

```
┌──────────────┐     ┌─────────────────────┐     ┌────────────────────────┐     ┌─────────────┐
│  AAS Client  │────▶│  BaSyx Submodel     │────▶│  Operation Delegation  │────▶│  MQTT Asset │
│  (Web UI)    │     │  Repository         │     │  Service               │     │  (PackML)   │
└──────────────┘     └─────────────────────┘     └────────────────────────┘     └─────────────┘
                              │                            │
                              │ invocationDelegation       │ MQTT Pub/Sub
                              │ qualifier in Operation     │
                              ▼                            ▼
                     HTTP POST to delegation URL    Command/Response
```

## How It Works

1. **AAS Operations** are defined with an `invocationDelegation` qualifier pointing to this service
2. When a user invokes an operation through BaSyx (via API or Web UI), BaSyx forwards the request
3. The service receives `OperationVariable[]` as input, extracts the values, and builds an MQTT command
4. The command is published to the configured MQTT topic with a correlation UUID
5. The service subscribes to the response topic and waits for a response with the matching UUID
6. Once received, the response is converted back to `OperationVariable[]` format and returned

## API Endpoints

### Health Check
```
GET /health
```
Returns `{"status": "healthy"}` if the service is running.

### Invoke Operation
```
POST /operations/<asset_id>/<skill_name>
Content-Type: application/json

Body: OperationVariable[]
```

Example:
```bash
curl -X POST http://localhost:8087/operations/planarTableShuttle1AAS/MoveToPosition \
  -H "Content-Type: application/json" \
  -d '[
    {
      "value": {
        "modelType": "Property",
        "idShort": "X",
        "valueType": "xs:double",
        "value": "100.0"
      }
    },
    {
      "value": {
        "modelType": "Property",
        "idShort": "Y",
        "valueType": "xs:double",
        "value": "200.0"
      }
    }
  ]'
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MQTT_BROKER` | `localhost` | MQTT broker hostname |
| `MQTT_PORT` | `1883` | MQTT broker port |
| `PORT` | `8087` | HTTP service port |
| `OPERATION_TIMEOUT` | `30` | Timeout in seconds for operation responses |
| `TOPIC_CONFIG_PATH` | `/app/config/topics.json` | Path to topic configuration file |

### Topic Configuration (topics.json)

Maps asset IDs and skill names to MQTT topics:

```json
{
    "planarTableShuttle1AAS": {
        "base_topic": "NN/Nybrovej/InnoLab/Planar/Xbot1",
        "skills": {
            "MoveToPosition": {
                "command_topic": "NN/Nybrovej/InnoLab/Planar/Xbot1/CMD/XYMotion",
                "response_topic": "NN/Nybrovej/InnoLab/Planar/Xbot1/DATA/XYMotion"
            }
        }
    }
}
```

## Running Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export MQTT_BROKER=localhost
export MQTT_PORT=1883
export PORT=8087

# Run the service
python operation_delegation_service.py
```

## Running with Docker

```bash
# Build the image
docker build -t operation-delegation .

# Run the container
docker run -p 8087:8087 \
  -e MQTT_BROKER=192.168.0.104 \
  -e MQTT_PORT=1883 \
  operation-delegation
```

## Integration with AAS Generator

The `generate_aas.py` script automatically adds `invocationDelegation` qualifiers to Operations:

```bash
# Generate AAS with custom delegation URL
python generate_aas.py --config Resource/configs/planarShuttle1.yaml \
  --delegation-url http://operation-delegation:8087

# Or set via environment variable
export DELEGATION_SERVICE_URL=http://operation-delegation:8087
python generate_aas.py --config Resource/configs/planarShuttle1.yaml
```

## MQTT Message Format

### Command Message (Published)
```json
{
    "Uuid": "550e8400-e29b-41d4-a716-446655440000",
    "X": 100.0,
    "Y": 200.0,
    "Velocity": 50.0
}
```

### Response Message (Expected)
```json
{
    "Uuid": "550e8400-e29b-41d4-a716-446655440000",
    "State": "SUCCESS",
    "X": 100.0,
    "Y": 200.0
}
```

The `State` field should be one of:
- `RUNNING` - Operation is in progress
- `SUCCESS` - Operation completed successfully
- `FAILURE` - Operation failed

## Troubleshooting

### Operation Timeout
- Check that the MQTT broker is accessible
- Verify the command and response topics are correct
- Ensure the asset is subscribing to the command topic
- Check that the response includes the correct UUID

### Connection Errors
- Verify MQTT broker hostname and port
- Check network connectivity between containers
- Review MQTT broker logs for connection attempts

## License
MIT License
