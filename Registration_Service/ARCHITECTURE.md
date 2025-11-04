# Registration Service Architecture

## Overview

The registration service has been refactored into a modular, maintainable architecture with clean separation of concerns.

## Structure

```
Registration_Service/
├── aas-registration-service.py    # CLI entry point (214 lines)
└── src/                            # Source package
    ├── __init__.py                 # Package exports
    ├── config.py                   # BaSyx configuration (19 lines)
    ├── parsers.py                  # AASX XML parsing (134 lines)
    ├── databridge.py               # DataBridge config generation (164 lines)
    ├── registry.py                 # BaSyx registration logic (501 lines)
    └── utils.py                    # Helper utilities (27 lines)
```

**Total:** 1,080 lines (previously 925 lines in one file)

## Modules

### `aas-registration-service.py` (CLI)
- **Purpose**: Command-line interface entry point
- **Responsibilities**:
  - Argument parsing (argparse)
  - Command routing (register, register-json, list, configure)
  - User-facing messages and error handling
- **Usage**: `python aas-registration-service.py --help`

### `src/config.py`
- **Purpose**: BaSyx server configuration
- **Classes**: `BaSyxConfig`
- **Responsibilities**:
  - Store BaSyx server URLs
  - Derive registry endpoints (ports 8082, 8083)

### `src/parsers.py`
- **Purpose**: AASX file parsing
- **Classes**: `AASXParser`
- **Responsibilities**:
  - Extract AAS shells from AASX XML
  - Extract submodels and properties
  - Parse XML with proper namespaces
- **Key Methods**:
  - `parse()`: Main entry point
  - `_extract_aas_data()`: Extract shells and submodels
  - `_extract_shell()`: Parse AAS shell
  - `_extract_submodel()`: Parse submodel
  - `_extract_property()`: Parse property with type info

### `src/databridge.py`
- **Purpose**: DataBridge configuration generation
- **Classes**: `DataBridgeConfigGenerator`
- **Responsibilities**:
  - Generate MQTT consumer configurations
  - Generate AAS server configurations
  - Generate JSONATA transformers (type-based conversion)
  - Generate route configurations
- **Key Methods**:
  - `generate_mqtt_consumer_config()`: MQTT topics with custom mappings
  - `generate_aas_server_config()`: AAS endpoint configs
  - `generate_jsonata_transformers()`: Auto-generate type converters
  - `_get_jsonata_for_type()`: Map XSD types to JSONATA expressions
  - `generate_routes_config()`: Data flow routes

**JSONATA Type Mappings:**
- `xs:double/float/int` → `$number($)`
- `xs:boolean` → `$boolean($)`
- `xs:string` → `$string($)`
- `xs:dateTime/date/time` → `$string($)` (ISO format)

### `src/registry.py`
- **Purpose**: BaSyx registration orchestration
- **Classes**: `BaSyxRegistrationService`
- **Responsibilities**:
  - Register AAS shells and submodels with BaSyx
  - Register shell/submodel descriptors with registries
  - Auto-generate concept descriptions
  - Orchestrate DataBridge configuration
  - Restart DataBridge container
- **Key Methods**:
  - `register_aasx()`: AASX file registration workflow
  - `register_from_json()`: JSON registration with custom topics
  - `_register_aas_shell_with_submodels()`: Shell with references
  - `_register_submodel()`: Submodel registration
  - `_register_shell_descriptor()`: AAS Registry (port 8082)
  - `_register_submodel_descriptor()`: Submodel Registry (port 8083)
  - `_register_concept_descriptions_from_submodels()`: Auto-generate CDs
  - `_generate_databridge_configs()`: Orchestrate config generation
  - `_restart_databridge()`: Docker container control
  - `list_shells()`: List registered shells

### `src/interface_parser.py`
- **Purpose**: Parse MQTT interface information from AAS
- **Classes**: `MQTTInterfaceParser`
- **Responsibilities**:
  - Parse IDTA Asset Interfaces Description submodels
  - Extract MQTT broker URL and base topic from EndpointMetadata
  - Parse actions (dispense, weigh, halt, etc.) from InteractionMetadata
  - Extract request/response topics and additional topics
  - Parse JSON schema references for input/output validation
  - Extract QoS, retain flags, and other MQTT properties
- **Key Methods**:
  - `parse_interface_submodels()`: Main parsing entry point
  - `extract_topic_mappings()`: Generate topic→property mappings
  - `_parse_interface_mqtt()`: Parse InterfaceMQTT element
  - `_parse_endpoint_metadata()`: Extract broker info and base topic
  - `_parse_interaction_metadata()`: Parse actions and properties
  - `_parse_actions()`: Extract action definitions with forms
  - `_parse_forms()`: Extract request/response topics from forms

**InterfaceMQTT Structure Support:**
```
EndpointMetadata/base: mqtt://host:port/base/topic
InteractionMetadata/actions/
  <action_name>/
    forms/href: /relative/topic/path
    forms/response/href: /response/topic
    forms/additionalResponses/href: /data/topic
    input: /schemas/input.schema.json
    output: /schemas/output.schema.json
```

### `src/utils.py`
- **Purpose**: Helper utilities
- **Functions**:
  - `save_json_file()`: Save JSON with formatting
  - `load_json_file()`: Load JSON file
  - `ensure_directory()`: Create directory if needed

## Automatic MQTT Topic Extraction

The registration service now automatically extracts MQTT topics from **IDTA Asset Interfaces Description** submodels (`InterfaceMQTT`). This eliminates the need for manual topic mappings in most cases.

### How It Works

1. **Parse InterfaceMQTT Submodel**: The service scans for `InterfaceMQTT` submodel element collections
2. **Extract Broker Info**: Parses `EndpointMetadata/base` (e.g., `mqtt://192.168.0.104:1883/NN/Nybrovej/InnoLab/Filling`)
3. **Parse Actions**: Extracts actions like `dispense`, `weigh`, `halt` from `InteractionMetadata/actions`
4. **Build Topic Paths**: Combines base topic with action-specific hrefs (e.g., `/CMD/Dispense/Request`)
5. **Generate Consumers**: Creates DataBridge MQTT consumers for all discovered topics

### Example: Filling System

```json
{
  "InterfaceMQTT": {
    "EndpointMetadata": {
      "base": "mqtt://192.168.0.104:1883/NN/Nybrovej/InnoLab/Filling"
    },
    "InteractionMetadata": {
      "actions": {
        "dispense": {
          "forms": {
            "href": "/CMD/Dispense/Request",
            "response": {
              "href": "/CMD/Dispense/Response"
            }
          },
          "input": "/schemas/command.schema.json",
          "output": "/schemas/commandResponse.schema.json"
        }
      }
    }
  }
}
```

**Generated Topics:**
- Request: `NN/Nybrovej/InnoLab/Filling/CMD/Dispense/Request`
- Response: `NN/Nybrovej/InnoLab/Filling/CMD/Dispense/Response`

### Benefits

✅ **Automatic Discovery**: No manual topic configuration needed  
✅ **Standards-Based**: Follows IDTA Asset Interfaces Description spec  
✅ **Schema Integration**: Links to JSON schemas for validation  
✅ **Broker Auto-Config**: Automatically uses broker from interface  
✅ **QoS Support**: Extracts MQTT QoS and retain settings  

## Usage Examples

### Import in Python
```python
from src import BaSyxConfig, BaSyxRegistrationService

# Initialize
config = BaSyxConfig(base_url='http://localhost:8081')
service = BaSyxRegistrationService(
    config=config,
    mqtt_broker='hivemq-broker',
    mqtt_port=1883
)

# Register from JSON
service.register_from_json('robot_registration.json')

# List shells
shells = service.list_shells()
```

### CLI Commands
```bash
# Register AASX file
python aas-registration-service.py register example-motor-fixed.aasx

# Register from JSON with custom topics
python aas-registration-service.py --basyx-url http://192.168.0.104:8081 \
    register-json robot_registration.json --mqtt-broker hivemq-broker

# List registered AAS
python aas-registration-service.py list

# Configure MQTT broker
python aas-registration-service.py configure --mqtt-broker 192.168.0.104
```

## Design Principles

1. **Separation of Concerns**: Each module has a single, well-defined responsibility
2. **Loose Coupling**: Modules communicate through clean interfaces
3. **High Cohesion**: Related functionality grouped together
4. **DRY (Don't Repeat Yourself)**: Common utilities extracted to utils.py
5. **Testability**: Modular structure enables unit testing
6. **Maintainability**: Smaller files are easier to understand and modify

## Benefits of Refactoring

- ✅ **Improved Readability**: ~200 lines per module vs 925 in one file
- ✅ **Better Organization**: Logical grouping of related functionality
- ✅ **Easier Maintenance**: Changes localized to specific modules
- ✅ **Enhanced Testability**: Each module can be tested independently
- ✅ **Reusability**: Modules can be imported and used separately
- ✅ **Scalability**: Easy to add new features without bloating files

## Development Workflow

1. **Make changes** to appropriate module (config, parsers, databridge, or registry)
2. **Update imports** in `src/__init__.py` if adding new classes
3. **Test locally** using CLI commands
4. **Verify integration** with full registration workflow

## Testing

```bash
# Test CLI help
python aas-registration-service.py --help

# Test with debug logging
python aas-registration-service.py --debug register-json robot_registration.json

# Test specific command
python aas-registration-service.py list
```

## Future Enhancements

- Add unit tests for each module
- Add integration tests for full workflows
- Add type hints validation (mypy)
- Add code coverage reporting
- Add API documentation (Sphinx)
- Add configuration file support (.env)
