# BaSyx AAS Registration Service

Automated registration service for Asset Administration Shells (AAS) in the BaSyx ecosystem.

## Features

- **AAS Registration**: Registers Shells, Submodels, and Concept Descriptions with BaSyx Repository and Registry.
- **DataBridge Configuration**: Automatically generates and applies DataBridge configurations (Consumers, Transformers, Routes, Sinks) based on AAS Interface Models.
- **MQTT Listener**: Listens for registration requests via MQTT for dynamic asset onboarding.
- **Format Support**: Supports both `.aasx` packages and JSON definitions.

## Installation

```bash
pip install -r requirements.txt
```

## Usage

### CLI Commands

```bash
# Register an AASX file
python aas-registration-service.py register path/to/file.aasx

# Register from a JSON definition
python aas-registration-service.py register-json path/to/data.json

# Liste registered shells
python aas-registration-service.py list
```

### MQTT Listener

Start the service in listening mode to accept dynamic registration requests:

```bash
python aas-registration-service.py listen \
  --mqtt-broker 192.168.0.104 \
  --mqtt-port 1883 \
  --databridge-name databridge
```

## Configuration

The service interacts with the following components (defaults):
- **BaSyx Environment**: `http://localhost:8081`
- **MQTT Broker**: `192.168.0.104:1883`
