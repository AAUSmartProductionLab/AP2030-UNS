# Configuration Guide

## Overview

The AP2030-UNS system has been updated to use environment variables and Docker service names instead of hardcoded IP addresses, making it portable across different machines and networks.

## Quick Start

1. **Copy the example environment file:**
   ```bash
   cp .env.example .env
   ```

2. **Edit the `.env` file** with your machine's IP address:
   ```bash
   # For Linux/Mac
   EXTERNAL_HOST=$(hostname -I | awk '{print $1}')
   
   # Or manually set it
   EXTERNAL_HOST=192.168.1.100  # Replace with your actual IP
   ```

3. **Start the services:**
   ```bash
   docker-compose up -d
   ```

## Environment Variables

### `.env` File Configuration

The `.env` file is the **single source of truth** for network configuration across all services. All services read from this centralized configuration.

#### External Access Configuration

- **`EXTERNAL_HOST`** (default: `192.168.0.104`)
  - Your machine's IP address accessible from outside the Docker network
  - Used by the AAS Web UI and other external services
  - **This is the primary variable you need to change when deploying on a different machine**
  - Example: `192.168.1.100` or `10.0.0.50`

#### Hardware Configuration

- **`PMC_IP`** (default: `192.168.0.199`)
  - Planar Motor Controller hardware IP address
  - Update this if your PMC is on a different IP

#### Internal Service Configuration (Advanced)

These are pre-configured for Docker deployment and typically don't need changes:

##### MQTT Configuration
- **`MQTT_BROKER`** (default: `hivemq-broker`)
  - MQTT broker hostname for services inside Docker
- **`MQTT_PORT`** (default: `1883`)
  - MQTT broker port

##### BaSyx Configuration
- **`BASYX_URL`** (default: `http://aas-env:8081`)
  - BaSyx AAS Environment URL for Python services
- **`BASYX_INTERNAL_URL`** (default: `http://aas-env:8081`)
  - Alternative internal URL for DataBridge
- **`DELEGATION_SERVICE_URL`** (default: `http://operation-delegation:8087`)
  - Operation Delegation Service URL
- **`AAS_SERVER`** (default: `aas-env`)
  - AAS server hostname (for C++ services)
- **`AAS_PORT`** (default: `8081`)
  - AAS server port
- **`AAS_REGISTRY`** (default: `aas-registry`)
  - AAS Registry hostname (for C++ services)
- **`AAS_REGISTRY_PORT`** (default: `8080`)
  - AAS Registry port

### Services Using Centralized Configuration

All services now read from the centralized `.env` file or use Docker service names:

1. **Python Services** (PackML Stations, Registration Service, etc.)
   - Read environment variables via `os.getenv()`
   - Fallback to Docker service names

2. **BaSyx Services** (AAS Environment, Dashboard API)
   - Use `${EXTERNAL_HOST}` in property files
   - Passed via docker-compose environment

3. **Frontend (Configurator)**
   - Uses `localhost` for browser access
   - Configurable via `.env` file in Configurator directory
   - Auto-detects host via `window.location.hostname`

4. **BT Controller (C++)**
   - Reads from `controller_config.yaml`
   - Supports `${VAR:-default}` syntax for environment variables
   - Environment variables passed via docker-compose

5. **Operation Delegation Service**
   - Fully environment-variable driven
   - No hardcoded values

## Internal Service Communication

Services running within Docker Compose use **service names** instead of IP addresses:

- **MQTT Broker**: `hivemq-broker:1883`
- **AAS Environment**: `aas-env:8081`
- **AAS Registry**: `aas-registry:8080`
- **Submodel Registry**: `sm-registry:8080`
- **AAS Discovery**: `aas-discovery:8081`
- **Operation Delegation**: `operation-delegation:8087`
- **TimescaleDB**: `timescaledb:5432`
- **MongoDB**: `mongo:27017`

These service names are automatically resolved within the Docker network.

## Accessing Services Externally

To access services from outside Docker (e.g., from your browser or external applications):

1. **Web Interfaces:**
   - HiveMQ Dashboard: `http://<EXTERNAL_HOST>:8091`
   - Configurator Frontend: `http://<EXTERNAL_HOST>:5173`
   - Grafana: `http://<EXTERNAL_HOST>:3000`
   - AAS Web UI: `http://<EXTERNAL_HOST>:3001`
   - Portainer: `http://<EXTERNAL_HOST>:9000`
   - Groot2: `http://<EXTERNAL_HOST>:6080`
   - MQTT Explorer: `http://<EXTERNAL_HOST>:4000`

2. **Service APIs:**
   - AAS Environment: `http://<EXTERNAL_HOST>:8081`
   - AAS Registry: `http://<EXTERNAL_HOST>:8082`
   - Submodel Registry: `http://<EXTERNAL_HOST>:8083`
   - AAS Discovery: `http://<EXTERNAL_HOST>:8084`
   - Dashboard API: `http://<EXTERNAL_HOST>:8085`
   - Operation Delegation: `http://<EXTERNAL_HOST>:8087`

3. **MQTT Broker:**
   - Connect to: `<EXTERNAL_HOST>:1883`

Replace `<EXTERNAL_HOST>` with the value you set in your `.env` file.

## Running on Different Machines

When moving the project to a different machine:

1. Update the `EXTERNAL_HOST` in `.env` with the new machine's IP
2. Update `PMC_IP` if the Planar Motor Controller location changed
3. Restart services: `docker-compose up -d`

That's it! No code changes required.

## Troubleshooting

### Services can't connect to each other

- **Within Docker**: Ensure you're using service names (e.g., `hivemq-broker`) not IP addresses
- **From host to Docker**: Use `localhost` or `127.0.0.1` with the mapped port
- **From external machine**: Use the `EXTERNAL_HOST` IP with the mapped port

### AAS Web UI shows connection errors

- Verify `EXTERNAL_HOST` in `.env` matches your machine's IP
- Check that the ports are accessible (not blocked by firewall)
- Restart the `aas-web-ui` service: `docker-compose restart aas-web-ui`

### Finding your machine's IP address

```bash
# Linux
hostname -I | awk '{print $1}'

# macOS
ipconfig getifaddr en0

# Windows (PowerShell)
(Get-NetIPAddress -AddressFamily IPv4 -InterfaceAlias "Ethernet").IPAddress
```

## Legacy Configuration

If you need to run services outside Docker (not recommended), set these environment variables:

```bash
# For Python services running outside Docker
export MQTT_BROKER=<your-ip>
export MQTT_PORT=1883
export BASYX_URL=http://<your-ip>:8081
export DELEGATION_SERVICE_URL=http://<your-ip>:8087

# Example:
export MQTT_BROKER=192.168.1.100
export MQTT_PORT=1883
export BASYX_URL=http://192.168.1.100:8081
export DELEGATION_SERVICE_URL=http://192.168.1.100:8087
```

The recommended approach is to run everything through Docker Compose for consistency.

## Distributed Deployment

When deploying services across multiple machines (e.g., running `bt_controller` on one machine while other services run on a different host), you need to configure environment variables to use IP addresses instead of Docker container names.

### Scenario: BT Controller on a Different Machine

If you want to run `bt_controller` on **Machine B** while the rest of the stack runs on **Machine A** (IP: `192.168.0.140`):

#### On Machine A (main stack):
Keep the default `.env` file. Services communicate internally via container names.

#### On Machine B (bt_controller only):
Create a `.env` file with IP addresses instead of container names:

```bash
# .env for distributed deployment
EXTERNAL_HOST=192.168.0.140

# Use IP addresses since container names won't resolve
MQTT_BROKER=192.168.0.140
MQTT_PORT=1883

AAS_SERVER=192.168.0.140
AAS_PORT=8081
AAS_REGISTRY=192.168.0.140
AAS_REGISTRY_PORT=8082
```

Then run only the bt_controller:
```bash
docker-compose up -d bt_controller
```

### Scenario: PackML Station on a Raspberry Pi

If running a physical station (e.g., `filling_station`) on a Raspberry Pi that needs to connect to the main stack:

```bash
# .env on Raspberry Pi
MQTT_BROKER=192.168.0.140
MQTT_PORT=1883
```

### Key Points for Distributed Deployment

1. **Container names only work within the same Docker network** - services on different hosts must use IP addresses
2. **EXTERNAL_HOST** should be set to the IP of the machine running the main stack
3. **All services have sensible defaults** - they use container names by default but can be overridden via environment variables
4. **Ports must be accessible** - ensure firewall rules allow traffic on ports 1883, 8081, 8082, 8083, 8087, etc.

### Supported Environment Variables for All Services

| Variable | Default (Docker) | Use for External |
|----------|------------------|------------------|
| `MQTT_BROKER` | hivemq-broker | IP of MQTT host |
| `MQTT_PORT` | 1883 | 1883 |
| `AAS_SERVER` | aas-env | IP of AAS host |
| `AAS_PORT` | 8081 | 8081 |
| `AAS_REGISTRY` | aas-registry | IP of registry host |
| `AAS_REGISTRY_PORT` | 8080 | 8082 (external port) |
| `DELEGATION_SERVICE` | operation-delegation | IP of delegation host |
| `EXTERNAL_HOST` | localhost | Public IP of main stack |

## Hardcoded Values That May Need Manual Updates

Some configuration files contain hardcoded IP addresses that are used for AAS metadata/documentation. These typically don't need to be changed for runtime, but you may want to update them for accuracy:

### AAS Resource Configuration Files
Located in `AASDescriptions/Resource/configs/*.yaml`:
- These contain `base: 'mqtt://192.168.0.104:1883/...'` for WoT interface descriptions
- The actual MQTT connections use environment variables at runtime
- Update these if you want accurate metadata in your AAS descriptions

### ESP32 Physical Stations
Located in `PackML_Stations/Physical-Stations/include/ESP32Module.h`:
- Contains hardcoded `mqttServer = "192.168.0.104"`
- Must be updated and reflashed to ESP32 devices when changing networks
- Consider adding WiFiManager or similar for runtime configuration

