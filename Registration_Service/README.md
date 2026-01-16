# Unified AAS Registration Service

A unified service for registering Asset Administration Shells (AAS) from YAML configuration files.

## Features

- **Config-based Registration**: Register assets directly from YAML configuration files (no need to transmit large AAS files)
- **Operation Delegation Integration**: Automatically generates `topics.json` for the Operation Delegation Service
- **DataBridge Configuration**: Generates DataBridge configurations directly from YAML configs
- **AAS Generation**: Generates full AAS descriptions using the AAS generator
- **BaSyx Registration**: Registers Shells, Submodels, and Concept Descriptions with BaSyx
- **MQTT Listener**: Listens for registration requests via MQTT for dynamic asset onboarding
- **Legacy Support**: Still supports `.aasx` packages and JSON definitions

## Installation

```bash
pip install -r requirements.txt
```

## Usage

### Preferred: Config-based Registration

```bash
# Register from a single YAML config
python unified-registration-service.py register-config AASDescriptions/Resource/configs/planarShuttle1.yaml

# Register all configs from a directory
python unified-registration-service.py register-dir AASDescriptions/Resource/configs/
```

### Generate Configurations Only

```bash
# Generate Operation Delegation topics.json
python unified-registration-service.py generate-topics AASDescriptions/Resource/configs/

# Generate DataBridge configurations
python unified-registration-service.py generate-databridge AASDescriptions/Resource/configs/
```

### MQTT Listener

Start the service in listening mode to accept dynamic registration requests:

```bash
python unified-registration-service.py listen \
  --mqtt-broker 192.168.0.104 \
  --mqtt-port 1883 \
  --databridge-name databridge
```

#### MQTT Message Formats

**Config-based registration** (preferred, on topic `NN/Nybrovej/InnoLab/Registration/Config`):
```json
{
  "requestId": "unique-id",
  "assetId": "planarTableShuttle1AAS",
  "config": {
    "planarTableShuttle1AAS": {
      "idShort": "planarTableShuttle1AAS",
      "id": "https://smartproductionlab.aau.dk/aas/planarTableShuttle1",
      ...
    }
  }
}
```

**Legacy AAS JSON** (on topic `NN/Nybrovej/InnoLab/Registration/Request`):
```json
{
  "requestId": "unique-id",
  "assetId": "planarTableShuttle1AAS",
  "aasData": {
    "assetAdministrationShells": [...],
    "submodels": [...]
  }
}
```

### Legacy Commands

```bash
# Register an AASX file
python unified-registration-service.py register path/to/file.aasx

# Register from a JSON definition
python unified-registration-service.py register-json path/to/data.json

# List registered shells
python unified-registration-service.py list
```

## Architecture

The unified service combines several components:

1. **ConfigParser**: Parses YAML configs and extracts MQTT interface information
2. **TopicsGenerator**: Creates `topics.json` for Operation Delegation Service
3. **DataBridgeFromConfig**: Generates DataBridge configs directly from YAML
4. **UnifiedRegistrationService**: Orchestrates the complete registration workflow
5. **MQTTConfigRegistrationService**: MQTT listener for dynamic registration

### Workflow

```
YAML Config → Parse → Generate topics.json → Generate DataBridge → Generate AAS → Register with BaSyx → Restart services
```

## Configuration

The service interacts with the following components (defaults):
- **BaSyx Environment**: `http://localhost:8081`
- **MQTT Broker**: `192.168.0.104:1883`
- **Operation Delegation**: `http://192.168.0.104:8087`

### Environment Variables

- `BASYX_URL`: BaSyx server URL
- `MQTT_BROKER`: MQTT broker hostname
- `MQTT_PORT`: MQTT broker port
- `DELEGATION_SERVICE_URL`: Operation Delegation Service URL

