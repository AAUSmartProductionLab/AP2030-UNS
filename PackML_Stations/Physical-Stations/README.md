# PackML State Machine Implementation for ESP32 Physical Stations

This directory contains the C++ implementation of PackML state machines for physical filling and stoppering stations controlled by ESP32 microcontrollers.

## Overview

The implementation mirrors the Python simulation structure, providing a standardized PackML ISA-88 compliant state machine for both stations. The architecture separates shared PackML logic from station-specific hardware control.

## Architecture

### Common Components

#### `PackMLStateMachine.h`
Core PackML state machine implementation shared by all stations. Provides:

- **State Management**: Full PackML state enumeration (IDLE, STARTING, EXECUTE, COMPLETING, etc.)
- **Queue System**: Process queue with UUID tracking for command registration/unregistration
- **MQTT Integration**: Automatic state and command status publishing
- **Command Handling**: Callback-based command registration and execution

Key Features:
- Asynchronous command execution
- Registration/unregistration of commands in process queue
- Automatic state transitions following PackML specifications
- ISO 8601 timestamp generation for all messages
- State and queue broadcasting via MQTT

### Station-Specific Components

#### Filling Station
- **Hardware**: DC motor controlled dispenser with limit switches
- **Commands**:
  - `Dispense`: Lower dispenser, wait, raise back up, publish weight
  - `Needle`: Attachment operation for needle positioning
- **Topics**:
  - CMD: `AAU/Fibigerstræde/Building14/FillingLine/Filling/CMD/{Dispense|Needle|Occupy|Release}`
  - DATA: `AAU/Fibigerstræde/Building14/FillingLine/Filling/DATA/{Dispense|Needle|Occupy|Release|State|Weight}`

#### Stoppering Station
- **Hardware**: Servo motor, linear actuator, DC motor for plunger mechanism
- **Commands**:
  - `Plunge`: Execute full stoppering sequence (DC down, servo, linear actuator, DC up)
- **Topics**:
  - CMD: `AAU/Fibigerstræde/Building14/FillingLine/Stoppering/CMD/{Plunge|Occupy|Release}`
  - DATA: `AAU/Fibigerstræde/Building14/FillingLine/Stoppering/DATA/{Plunge|Occupy|Release|State}`

## File Structure

```
Physical-Stations/
├── include/
│   ├── PackMLStateMachine.h           # Common PackML state machine
│   ├── filling_station.h              # Filling hardware control
│   ├── stoppering_station.h           # Stoppering hardware control
│   ├── wifi_mqtt_setup_filling.h      # Filling MQTT/WiFi config
│   └── wifi_mqtt_setup_stoppering.h   # Stoppering MQTT/WiFi config
├── src/
│   ├── MQTT_Filling.cpp               # Filling station main
│   └── MQTT_Stoppering.cpp            # Stoppering station main
└── platformio.ini                     # PlatformIO configuration
```

## PackML State Flow

```
IDLE → STARTING → EXECUTE → COMPLETING → COMPLETE → RESETTING → IDLE
                     ↓
                  ABORTING → ABORTED → CLEARING → STOPPED
```

### State Descriptions

- **IDLE**: Waiting for commands in queue
- **STARTING**: Preparing to execute next command from queue
- **EXECUTE**: Actively executing command process function
- **COMPLETING**: Cleaning up after successful execution
- **COMPLETE**: Command completed successfully
- **RESETTING**: Returning to idle state
- **ABORTING**: Interrupting current process and clearing queue
- **ABORTED**: All processes stopped, queue cleared

## Command Protocol

### Command Message Format
```json
{
  "Uuid": "unique-command-identifier",
  "TimeStamp": "2024-11-24T10:30:00.000Z"
}
```

### Response Message Format
```json
{
  "State": "RUNNING|SUCCESS|FAILURE",
  "Uuid": "unique-command-identifier",
  "TimeStamp": "2024-11-24T10:30:05.000Z"
}
```

### State Message Format
```json
{
  "State": "IDLE|STARTING|EXECUTE|...",
  "TimeStamp": "2024-11-24T10:30:00.000Z",
  "ProcessQueue": ["uuid1", "uuid2", "uuid3"]
}
```

## Registration System

Commands must beoccupied before execution:

1. **Occupy Command**: Send to `{BASE_TOPIC}/CMD/Occupy` with Uuid
2. **State Machine**: 
   - Publishes `RUNNING` on `/DATA/Occupy`
   - Adds UUID to process queue
   - When command reaches front of queue, publishes `SUCCESS`
3. **Execute Command**: Send actual command (Dispense/Plunge) with same Uuid
4. **Execution States**: State machine publishes `RUNNING` → `SUCCESS`/`FAILURE`

### Unregistration

Commands can be removed from queue:
- Send to `{BASE_TOPIC}/CMD/Release` with Uuid
- Cannot release currently executing commands
- Successfully releaseed commands publish `SUCCESS`, failures publish `FAILURE`

## Usage Example

```cpp
// In setup()
stateMachine = new PackMLStateMachine("AAU/.../Filling", &client);
stateMachine->begin();

// Occupy command handler
stateMachine->registerCommandHandler(
  "AAU/.../Filling/CMD/Dispense",
  "AAU/.../Filling/DATA/Dispense",
  [](PackMLStateMachine* sm, const JsonDocument& msg) {
    sm->executeCommand(msg, dataTopic, FillingRunning);
  },
  FillingRunning
);

// In loop()
client.loop();
stateMachine->loop();

// In callback()
JsonDocument doc;
deserializeJson(doc, payload);
stateMachine->handleMessage(topic, doc);
```

## Key Differences from Python Implementation

1. **Memory Management**: Uses dynamic allocation for state machine, vectors for queues
2. **Threading**: ESP32 single-threaded; delays block execution (acceptable for physical processes)
3. **JSON Handling**: Uses ArduinoJson library instead of Python's json module
4. **Time Handling**: Uses ESP32 time.h with NTP synchronization
5. **MQTT Client**: Uses PubSubClient library instead of paho-mqtt

## Dependencies

- **ArduinoJson**: JSON serialization/deserialization
- **PubSubClient**: MQTT client library
- **ESP32Servo**: Servo motor control (stoppering only)
- **WiFi**: ESP32 WiFi library

## Configuration

### WiFi Settings
Edit in `wifi_mqtt_setup_{filling|stoppering}.h`:
```cpp
const char *ssid = "AP2030";
const char *pass = "NovoNordisk";
const char *mqtt_serv = "192.168.0.104";
```

### Topics
Modify base topics in setup() call:
```cpp
stateMachine = new PackMLStateMachine("Your/Base/Topic", &client);
```

## Hardware Considerations

Both stations perform blocking operations during execution:
- **Filling**: Motor movements with timeout protection (8s max)
- **Stoppering**: Sequential operations with fixed delays

These blocking operations are acceptable as:
1. Physical processes cannot be interrupted safely
2. State machine handles queue during IDLE periods
3. MQTT loop maintains connection between executions

## Troubleshooting

### Connection Issues
- Verify WiFi credentials and MQTT broker address
- Check NTP server accessibility for timestamp generation
- Monitor serial output for connection status

### Command Not Executing
- Ensure command isoccupied before execution
- Verify UUID matches between occupy and execute
- Check state machine is in EXECUTE state
- Confirm correct topic format

### Queue Management
- Commands execute in FIFO order
- Only front command can execute
- Use release to remove queued commands
- Abort clears entire queue

## Future Enhancements

Potential improvements aligned with Python version:
- Error recovery mechanisms
- Process interruption support
- Dynamic timeout configuration
- Extended diagnostics and logging
- Hold/Suspend state implementations
