# Network Configuration Architecture

## Single Source of Truth: `.env` File

The AP2030-UNS system uses a **centralized configuration approach** where all network settings are defined in the root `.env` file. This eliminates hardcoded IP addresses and makes the system portable across different machines.

## Configuration Flow

```
┌─────────────────────────────────────────────────────────────┐
│                      Root .env File                          │
│  EXTERNAL_HOST=192.168.0.104                                │
│  MQTT_BROKER=hivemq-broker                                  │
│  AAS_SERVER=aas-env                                         │
│  ... (all network configuration)                            │
└─────────────────────┬───────────────────────────────────────┘
                      │
        ┌─────────────┼─────────────┬──────────────┐
        │             │             │              │
        ▼             ▼             ▼              ▼
┌──────────────┐ ┌──────────┐ ┌──────────┐ ┌────────────┐
│docker-compose│ │ Python   │ │ BaSyx    │ │Configurator│
│    .yml      │ │ Services │ │ Services │ │  Frontend  │
└──────┬───────┘ └────┬─────┘ └────┬─────┘ └─────┬──────┘
       │              │            │             │
       │ Passes env   │ Reads via  │ Uses ${VAR} │ Browser
       │ to containers│ os.getenv()│ in .properties │ access
       │              │            │             │
       ▼              ▼            ▼             ▼
  All Services    PackML       aas-env.      localhost
  get correct     Stations     properties    (auto-detect)
  configuration   Reg Service
```

## Configuration by Component

### 1. Docker Compose (`docker-compose.yml`)
**Role**: Orchestrator that passes environment variables to containers

**Variables Passed**:
- `EXTERNAL_HOST` → aas-env, aas-web-ui, dashboard-api
- `MQTT_BROKER`, `MQTT_PORT` → all station services
- `AAS_SERVER`, `AAS_PORT`, `AAS_REGISTRY` → bt_controller
- `PMC_IP` → planar_controller

**Why**: Ensures each container gets the right configuration without hardcoding

### 2. Python Services

#### PackML Stations (`cameraProxy.py`, `fillingProxy.py`, etc.)
```python
BROKER_ADDRESS = os.getenv("MQTT_BROKER", "hivemq-broker")
BROKER_PORT = int(os.getenv("MQTT_PORT", "1883"))
```

#### Registration Service (`src/core/constants.py`)
```python
DEFAULT_MQTT_BROKER = os.environ.get("MQTT_BROKER", "hivemq-broker")
DEFAULT_BASYX_URL = os.environ.get("BASYX_URL", "http://aas-env:8081")
EXTERNAL_BASYX_HOST = os.environ.get("EXTERNAL_HOST", "localhost")
```

**Why**: Python can easily read environment variables, with Docker service names as fallbacks

### 3. BaSyx Services

#### AAS Environment (`basyx/aas-env.properties`)
```properties
basyx.externalurl=http://${EXTERNAL_HOST:localhost}:8081
mqtt.hostname=hivemq-broker
```

#### Dashboard API (`basyx/aas-dashboard.yml`)
```yaml
basyx:
  externalurl: http://${EXTERNAL_HOST:localhost}:8085
```

**Why**: BaSyx properties files support `${VAR:default}` syntax for environment variables

### 4. BT Controller (C++)

#### Configuration (`BT_Controller/config/controller_config.yaml`)
```yaml
mqtt:
  broker_uri: "tcp://${MQTT_BROKER:-hivemq-broker}:${MQTT_PORT:-1883}"
aas:
  server_url: "http://${AAS_SERVER:-aas-env}:${AAS_PORT:-8081}"
  registry_url: "http://${AAS_REGISTRY:-aas-registry}:${AAS_REGISTRY_PORT:-8080}"
```

**Why**: C++ applications typically use config files; environment variable substitution handled at runtime

### 5. Configurator Frontend (React/Vite)

#### Environment (`.env`)
```bash
VITE_AAS_REPOSITORY_URL=http://localhost:8081
VITE_AAS_SHELL_REGISTRY_URL=http://localhost:8082
```

#### Runtime Detection (`AasService.jsx`, `Settings.jsx`, `Homepage.jsx`)
```javascript
const defaultHost = window.location.hostname || 'localhost';
```

**Why**: Frontend runs in browser, accesses services via host machine's exposed ports

## Default Values Strategy

### Internal Communication (Within Docker Network)
**Use Docker service names**:
- `hivemq-broker` instead of `192.168.0.104`
- `aas-env` instead of `192.168.0.104:8081`
- `aas-registry` instead of `192.168.0.104:8082`

**Benefit**: Works on any machine without configuration changes

### External Communication (From Browser/Host)
**Use dynamic detection or localhost**:
- Browser: `window.location.hostname` (auto-detects)
- Development: `localhost` (port forwarding)
- Production: Set `EXTERNAL_HOST` in `.env`

**Benefit**: Adapts to deployment environment automatically

## Network Topology

```
┌─────────────────────────────────────────────────────────────────┐
│                        Host Machine                             │
│  IP: ${EXTERNAL_HOST} (e.g., 192.168.0.104)                    │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │              Docker Network (hivemq-network)              │ │
│  │                                                           │ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐ │ │
│  │  │ hivemq-  │  │ aas-env  │  │ aas-     │  │stations  │ │ │
│  │  │ broker   │  │:8081     │  │ registry │  │          │ │ │
│  │  │:1883     │  │          │  │:8080     │  │          │ │ │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘ │ │
│  │       ▲             ▲             ▲             ▲        │ │
│  │       │             │             │             │        │ │
│  │       └─────────────┴─────────────┴─────────────┘        │ │
│  │         Internal: Use service names (hivemq-broker)      │ │
│  └───────────────────────────────────────────────────────────┘ │
│         │         │         │         │                        │
│   Port Mapping:                                                │
│   1883:1883  8081:8081  8082:8082  5173:5173  ...             │
└─────┼─────────┼─────────┼─────────┼────────────────────────────┘
      │         │         │         │
      │  External Access: Use ${EXTERNAL_HOST}:port or localhost:port
      ▼         ▼         ▼         ▼
   Browser   MQTT     AAS Web   Configurator
   Tools    Clients     UI        UI
```

## Migration Checklist

When deploying on a new machine:

- [ ] Update `EXTERNAL_HOST` in `.env` to new machine's IP
- [ ] Update `PMC_IP` if Planar Motor Controller IP changed
- [ ] Run `docker-compose up -d`
- [ ] Access services via new `EXTERNAL_HOST` IP

**That's it!** No code changes, no config file edits in subdirectories.

## Verification

### Check Configuration is Applied

```bash
# 1. Check environment variables in a container
docker exec bt_controller env | grep -E "MQTT|AAS"

# 2. Check resolved BaSyx configuration
docker exec aas-env cat /application/application.properties | grep externalurl

# 3. Verify frontend can connect
curl http://localhost:8081/shells

# 4. Check MQTT connectivity
docker exec hivemq-broker /opt/hivemq/tools/mqtt-cli/bin/mqtt pub \
  -h localhost -t test/topic -m "test"
```

## Troubleshooting

### Services can't find each other
- **Symptom**: Connection refused, timeout errors
- **Fix**: Ensure using Docker service names (e.g., `hivemq-broker`) not IPs
- **Check**: `docker-compose logs <service-name>`

### Frontend can't connect to AAS
- **Symptom**: CORS errors, network errors in browser
- **Fix**: Use `localhost:8081` or `${EXTERNAL_HOST}:8081`
- **Check**: Browser DevTools → Network tab

### Wrong external URL in AAS Web UI
- **Symptom**: Links point to wrong IP address
- **Fix**: Update `EXTERNAL_HOST` in `.env` and restart: `docker-compose restart aas-env aas-web-ui`
- **Verify**: `docker exec aas-env env | grep EXTERNAL_HOST`

## Files Modified

All files now reference the centralized `.env` configuration:

### Configuration Files
- ✅ `/workspaces/AP2030-UNS/.env` (primary source of truth)
- ✅ `/workspaces/AP2030-UNS/.env.example` (template)
- ✅ `/workspaces/AP2030-UNS/docker-compose.yml` (orchestrator)

### BaSyx
- ✅ `basyx/aas-env.properties`
- ✅ `basyx/aas-dashboard.yml`

### Python Services
- ✅ `PackML_Stations/*.py` (all proxy files)
- ✅ `Registration_Service/src/core/constants.py`
- ✅ `Registration_Service/src/config.py`
- ✅ `Registration_Service/src/generate_aas.py`

### Frontend
- ✅ `Configurator/.env`
- ✅ `Configurator/.env.example`
- ✅ `Configurator/src/services/AasService.jsx`
- ✅ `Configurator/src/pages/Homepage.jsx`
- ✅ `Configurator/src/pages/Settings.jsx`

### BT Controller
- ✅ `BT_Controller/config/controller_config.yaml`

### Data Configuration
- ✅ `mqttconsumer.json` (uses service names)
- ✅ `databridge/` configurations

## Benefits of This Architecture

1. **Portability**: Deploy on any machine by changing one variable
2. **Consistency**: All services use the same configuration
3. **Maintainability**: Single file to update
4. **Docker-Native**: Uses service discovery for internal communication
5. **Development-Friendly**: Works with localhost for development
6. **Production-Ready**: Easy to configure for different environments
