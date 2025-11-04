# MQTT Topic Auto-Extraction from InterfaceMQTT

## Overview

The registration service now automatically extracts MQTT topics from **IDTA Asset Interfaces Description** submodels, specifically the `InterfaceMQTT` element. This feature eliminates manual topic configuration and ensures standards-compliant MQTT integration.

## Features

### ✅ Automatic Topic Discovery
- Parses `InterfaceMQTT` submodel element collections
- Extracts broker URL, port, and base topic from `EndpointMetadata`
- Discovers actions (commands) from `InteractionMetadata`
- Builds complete topic paths by combining base + relative hrefs

### ✅ Action-Based Topic Mapping
For each action (e.g., `dispense`, `weigh`, `halt`):
- **Request Topic**: Extracted from `forms/href` (for subscribing to commands)
- **Response Topic**: Extracted from `forms/response/href` (for publishing responses)
- **Additional Topics**: Extracted from `forms/additionalResponses` (for data publications)

### ✅ Schema Integration
- Links JSON schemas for input/output validation
- Schemas referenced in `input` and `output` File elements
- Schema paths: `/schemas/command.schema.json`, `/schemas/commandResponse.schema.json`, etc.

### ✅ MQTT Properties
- QoS levels from `mqv_qos`
- Retain flags from `mqv_retain`
- Control packet types from `mqv_controlPacket`

### ✅ Automatic BaSyx Compatibility Fixes
- Converts invalid `valueType` values (e.g., `application/schema+json`) to `xs:string`
- Ensures all Property elements have valid XSD types
- Removes invalid `valueType` from File elements

## Example: Filling System

### Input AAS Structure
```json
{
  "submodels": [{
    "idShort": "AssetInterfacesDescription",
    "submodelElements": [{
      "idShort": "InterfaceMQTT",
      "modelType": "SubmodelElementCollection",
      "value": [
        {
          "idShort": "EndpointMetadata",
          "value": [{
            "idShort": "base",
            "value": "mqtt://192.168.0.104:1883/NN/Nybrovej/InnoLab/Filling"
          }]
        },
        {
          "idShort": "InteractionMetadata",
          "value": [{
            "idShort": "actions",
            "value": [{
              "idShort": "dispense",
              "value": [
                {
                  "idShort": "forms",
                  "value": [
                    {"idShort": "href", "value": "/CMD/Dispense/Request"},
                    {
                      "idShort": "response",
                      "value": [{"idShort": "href", "value": "/CMD/Dispense/Response"}]
                    }
                  ]
                }
              ]
            }]
          }]
        }
      ]
    }]
  }]
}
```

### Generated MQTT Consumers
```json
[
  {
    "uniqueId": "action_dispense_request",
    "serverUrl": "192.168.0.104",
    "serverPort": 1883,
    "topic": "NN/Nybrovej/InnoLab/Filling/CMD/Dispense/Request"
  },
  {
    "uniqueId": "action_weigh_request",
    "serverUrl": "192.168.0.104",
    "serverPort": 1883,
    "topic": "NN/Nybrovej/InnoLab/Filling/CMD/Weigh/Request"
  },
  {
    "uniqueId": "action_weigh_additional_0",
    "serverUrl": "192.168.0.104",
    "serverPort": 1883,
    "topic": "NN/Nybrovej/InnoLab/Filling/DATA/Weight"
  },
  {
    "uniqueId": "action_halt_request",
    "serverUrl": "192.168.0.104",
    "serverPort": 1883,
    "topic": "NN/Nybrovej/InnoLab/Filling/CMD/Halt/Request"
  }
]
```

### Extracted Topic Mappings
```
NN/Nybrovej/InnoLab/Filling/CMD/Dispense/Request  → Actions/dispense/Request
NN/Nybrovej/InnoLab/Filling/CMD/Dispense/Response → Actions/dispense/Response
NN/Nybrovej/InnoLab/Filling/CMD/Weigh/Request     → Actions/weigh/Request
NN/Nybrovej/InnoLab/Filling/CMD/Weigh/Response    → Actions/weigh/Response
NN/Nybrovej/InnoLab/Filling/DATA/Weight           → Actions/weigh/AdditionalData
NN/Nybrovej/InnoLab/Filling/CMD/Halt/Request      → Actions/halt/Request
```

## Registration Process

### 1. Parse InterfaceMQTT
```python
from src import MQTTInterfaceParser

parser = MQTTInterfaceParser()
interface_info = parser.parse_interface_submodels(submodels)
```

### 2. Extract Information
```python
{
  'broker_host': '192.168.0.104',
  'broker_port': 1883,
  'base_topic': 'NN/Nybrovej/InnoLab/Filling',
  'actions': {
    'dispense': {
      'request_topic': 'NN/Nybrovej/InnoLab/Filling/CMD/Dispense/Request',
      'response_topic': 'NN/Nybrovej/InnoLab/Filling/CMD/Dispense/Response',
      'input_schema': '/schemas/command.schema.json',
      'output_schema': '/schemas/commandResponse.schema.json',
      'qos': 2
    }
  }
}
```

### 3. Generate DataBridge Configs
- **MQTT Consumers**: Subscribe to request topics
- **AAS Servers**: Map to AAS submodel properties
- **JSONATA Transformers**: Type conversion based on schemas
- **Routes**: Connect consumers → transformers → AAS

### 4. Register with BaSyx
- **Repository**: Stores AAS shells and submodels
- **Shell Registry**: Port 8082, shell descriptors
- **Submodel Registry**: Port 8083, submodel descriptors
- **Concept Descriptions**: Auto-generated from semanticIds

## Usage

### CLI
```bash
# Register with automatic topic extraction
python aas-registration-service.py register-json filling_system.json

# With custom BaSyx URL
python aas-registration-service.py --basyx-url http://192.168.0.104:8081 \
    register-json filling_system.json
```

### Python API
```python
from src import BaSyxConfig, BaSyxRegistrationService

config = BaSyxConfig(base_url='http://192.168.0.104:8081')
service = BaSyxRegistrationService(config=config)

# Topics automatically extracted from InterfaceMQTT
service.register_from_json('filling_system.json')
```

## Benefits

### 📋 Standards Compliance
- Follows IDTA Asset Interfaces Description specification
- Compatible with W3C Web of Things (WoT) Thing Description
- Interoperable with other AAS tools

### 🔧 Zero Configuration
- No manual topic mapping required
- Broker settings auto-discovered
- QoS and MQTT properties extracted

### 🔄 Automatic Updates
- Change topics in AAS → Re-register → DataBridge updated
- Single source of truth for interface definitions
- Version control for interface changes

### ✅ Validation Ready
- JSON schemas linked for input/output
- Type-safe MQTT message processing
- Schema-based validation in DataBridge

## Troubleshooting

### Issue: Submodel registration fails with 400 error
**Cause**: Invalid `valueType` in Property or File elements  
**Solution**: Service automatically fixes these during preprocessing

### Issue: Topics not extracted
**Cause**: Missing or incorrectly structured InterfaceMQTT  
**Solution**: Check logs for parsing warnings, verify structure matches IDTA spec

### Issue: Broker not auto-configured
**Cause**: `EndpointMetadata/base` not in correct format  
**Expected format**: `mqtt://host:port/base/topic`

### Issue: Actions not found
**Cause**: Actions not in `InteractionMetadata/actions`  
**Solution**: Ensure actions are in correct SMC structure

## File Structure

```
Registration_Service/
├── filling_system.json              # Example with InterfaceMQTT
├── src/
│   ├── interface_parser.py          # NEW: MQTT interface parser
│   ├── registry.py                  # Updated: Uses interface parser
│   ├── databridge.py                # Updated: Interface-aware configs
│   └── ...
└── ../schemas/                      # JSON schemas for validation
    ├── command.schema.json
    ├── commandResponse.schema.json
    └── ...
```

## Related Standards

- **IDTA Asset Interfaces Description**: [Specification](https://industrialdigitaltwin.org/)
- **W3C WoT Thing Description**: [Specification](https://www.w3.org/TR/wot-thing-description/)
- **Eclipse BaSyx**: [Documentation](https://wiki.basyx.org/)
- **MQTT**: [MQTT 3.1.1 Specification](https://mqtt.org/)

## Future Enhancements

- [ ] Support for properties (not just actions)
- [ ] Support for events (MQTT subscriptions)
- [ ] OAuth/TLS configuration extraction
- [ ] Multiple interface protocols (HTTP, OPC-UA)
- [ ] Automatic schema validation on registration
- [ ] Interface versioning support
