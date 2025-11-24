#include "PackMLStateMachine.h"
// Implementation

PackMLStateMachine::PackMLStateMachine(const String &baseTopic, PubSubClient *mqttClient, WiFiClient *wifiClient)
    : state(PackMLState::RESETTING), baseTopic(baseTopic), client(mqttClient), wifiClient(wifiClient),
      isProcessing(false), currentProcessingUuid(""), currentUuid(""), subscriptionsInitialized(false), wifiMqttInitialized(false)
{
    occupyCmdTopic = baseTopic + "/CMD/Occupy";
    occupyDataTopic = baseTopic + "/DATA/Occupy";
    releaseCmdTopic = baseTopic + "/CMD/Release";
    releaseDataTopic = baseTopic + "/DATA/Release";
    stateDataTopic = baseTopic + "/DATA/State";
}

void PackMLStateMachine::initWiFiAndMQTT()
{
    WiFi.begin(config.ssid, config.password);
    while (WiFi.status() != WL_CONNECTED)
    {
        delay(500);
        Serial.print(".");
    }
    Serial.println("WiFi Connected");

    client->setServer(config.mqttServer, config.mqttPort);
    wifiMqttInitialized = true;
}

void PackMLStateMachine::subscribeToTopics()
{
    if (subscriptionsInitialized)
    {
        return; // Already subscribed
    }

    // Subscribe to occupy and release topics
    client->subscribe(occupyCmdTopic.c_str());
    client->subscribe(releaseCmdTopic.c_str());
    Serial.println("Subscribed to Occupy/Release topics");

    // Subscribe to all registered command handler topics
    for (const auto &handler : commandHandlers)
    {
        client->subscribe(handler.cmdTopic.c_str());
        Serial.print("Subscribed to: ");
        Serial.println(handler.cmdTopic);
    }

    subscriptionsInitialized = true;
}

void PackMLStateMachine::reconnect()
{
    // Don't attempt reconnection if WiFi/MQTT haven't been initialized yet
    if (!wifiMqttInitialized)
    {
        return;
    }

    while (!client->connected())
    {
        String clientId = "ESP32Client-" + String(random(0xffff), HEX);
        JsonDocument doc;
        doc["clientId"] = clientId;
        char output[100];

        if (client->connect(clientId.c_str()))
        {
            subscribeToTopics();
            publishState();
        }
        else
        {
            delay(5000);
        }
    }
}

void PackMLStateMachine::initializeTime()
{
    // Set Danish time with automatic daylight saving
    configTzTime("CET-1CEST,M3.5.0/02,M10.5.0/03", "pool.ntp.org", "time.nist.gov");

    struct tm timeinfo;
    Serial.print("Waiting for NTP time");
    for (int i = 0; i < 10; i++)
    {
        if (getLocalTime(&timeinfo))
        {
            Serial.println(" → Time OK");
            return;
        }
        Serial.print(".");
        delay(1000);
    }
    Serial.println("\n⚠️ Could not get time from NTP server");
}

void PackMLStateMachine::begin()
{
    // Note: Subscriptions and initial state publishing will be done after WiFi/MQTT initialization
    Serial.println("PackML State Machine beginning initialization");

    // Trigger the initial state transition from RESETTING
    resettingState();
}

void PackMLStateMachine::registerCommandHandler(const String &cmdTopic, const String &dataTopic,
                                                CommandCallback callback, void (*processFunc)())
{
    CommandHandler handler;
    handler.cmdTopic = baseTopic + cmdTopic;
    handler.dataTopic = baseTopic + dataTopic;
    handler.callback = callback;
    handler.processFunction = processFunc;
    commandHandlers.push_back(handler);

    Serial.print("Registered command handler for: ");
    Serial.println(handler.cmdTopic);
}

void PackMLStateMachine::handleMessage(const String &topic, const JsonDocument &message)
{
    // Check if it's aoccupy/release command
    if (topic == occupyCmdTopic)
    {
        occupyCallback(this, message);
        return;
    }
    if (topic == releaseCmdTopic)
    {
        releaseCallback(this, message);
        return;
    }

    // Check command handlers
    for (const auto &handler : commandHandlers)
    {
        if (topic == handler.cmdTopic)
        {
            if (handler.callback)
            {
                handler.callback(this, message);
            }
            return;
        }
    }
}

void PackMLStateMachine::executeCommand(const JsonDocument &message, const String &dataTopic,
                                        void (*processFunction)())
{
    if (state == PackMLState::EXECUTE)
    {
        String commandUuid = message["Uuid"].as<String>();
        String topic = baseTopic + String(dataTopic);
        // Check if this command is at the front of the queue
        if (uuids.empty() || uuids[0] != commandUuid)
        {
            Serial.print("Command UUID ");
            Serial.print(commandUuid);
            Serial.println(" not at front of queue. Ignoring.");
            return;
        }

        // Mark as processing
        isProcessing = true;
        currentProcessingUuid = commandUuid;

        // Publish RUNNING status
        publishCommandStatus(topic, commandUuid, "RUNNING");

        // Execute the process function
        if (processFunction)
        {
            processFunction();
        }

        // Mark completion
        publishCommandStatus(topic, commandUuid, "SUCCESS");
        isProcessing = false;
        currentProcessingUuid = "";

        // // Transition to completing state
        // transitionTo(PackMLState::COMPLETING, commandUuid);
    }
    else
    {
        Serial.print("Not in EXECUTE state. Current state: ");
        Serial.println(stateToString(state).c_str());
    }
}

void PackMLStateMachine::occupyCommand(const String &uuid)
{
    // Check if alreadyoccupyed
    for (const auto &existingUuid : uuids)
    {
        if (existingUuid == uuid)
        {
            Serial.println("UUID alreadyoccupyed");
            return;
        }
    }
    if (currentProcessingUuid == uuid)
    {
        Serial.println("UUID currently processing");
        return;
    }

    // Add to queue
    uuids.push_back(uuid);
    pendingRegistrations.push_back(uuid);

    // Publish RUNNING for registration
    publishCommandStatus(occupyDataTopic.c_str(), uuid, "RUNNING");

    publishState();

    // If idle, start processing
    if (state == PackMLState::IDLE)
    {
        transitionTo(PackMLState::STARTING);
    }
}

void PackMLStateMachine::releaseCommand(const String &uuid)
{
    bool found = false;

    // Check if currently processing
    if (isProcessing && uuid == currentProcessingUuid)
    {
        Serial.println("Cannot release: command is currently processing");
        publishCommandStatus(releaseDataTopic.c_str(), uuid, "FAILURE");
        return;
    }

    // Check if at front of queue
    if (!uuids.empty() && uuid == uuids[0] && !isProcessing)
    {
        uuids.erase(uuids.begin());

        // Remove from pending registrations
        for (size_t i = 0; i < pendingRegistrations.size(); i++)
        {
            if (pendingRegistrations[i] == uuid)
            {
                pendingRegistrations.erase(pendingRegistrations.begin() + i);
                publishCommandStatus(occupyDataTopic.c_str(), uuid, "FAILURE");
                break;
            }
        }

        publishCommandStatus(releaseDataTopic.c_str(), uuid, "SUCCESS");
        publishState();
        found = true;

        // Transition back to idle or start next
        if (uuids.empty())
        {
            transitionTo(PackMLState::RESETTING);
        }
        else
        {
            transitionTo(PackMLState::STARTING);
        }
        return;
    }

    // Check if in queue
    for (size_t i = 0; i < uuids.size(); i++)
    {
        if (uuids[i] == uuid)
        {
            uuids.erase(uuids.begin() + i);

            // Remove from pending registrations
            for (size_t j = 0; j < pendingRegistrations.size(); j++)
            {
                if (pendingRegistrations[j] == uuid)
                {
                    pendingRegistrations.erase(pendingRegistrations.begin() + j);
                    publishCommandStatus(occupyDataTopic.c_str(), uuid, "FAILURE");
                    break;
                }
            }

            publishCommandStatus(releaseDataTopic.c_str(), uuid, "SUCCESS");
            publishState();
            found = true;
            break;
        }
    }

    if (!found)
    {
        publishCommandStatus(releaseDataTopic.c_str(), uuid, "FAILURE");
    }
}

void PackMLStateMachine::abortCommand()
{
    Serial.println("Abort command received");

    // Clear the queue and transition to aborting
    String abortedUuid = isProcessing ? currentProcessingUuid : "#";
    transitionTo(PackMLState::ABORTING, abortedUuid);
}

void PackMLStateMachine::occupyCallback(PackMLStateMachine *sm, const JsonDocument &message)
{
    String commandUuid = message["Uuid"].as<String>();
    if (commandUuid.isEmpty())
    {
        Serial.println("No Uuid inoccupy command");
        return;
    }
    sm->occupyCommand(commandUuid);
}

void PackMLStateMachine::releaseCallback(PackMLStateMachine *sm, const JsonDocument &message)
{
    String commandUuid = message["Uuid"].as<String>();
    if (commandUuid.isEmpty())
    {
        Serial.println("No Uuid in release command");
        return;
    }
    sm->releaseCommand(commandUuid);
}

void PackMLStateMachine::loop()
{
    // State machine doesn't need continuous loop processing
    // All state transitions are event-driven through callbacks
}

// State transition methods
void PackMLStateMachine::transitionTo(PackMLState newState, const String &uuidParam)
{
    state = newState;
    publishState();

    Serial.print("Transitioned to state: ");
    Serial.println(stateToString(state).c_str());

    switch (newState)
    {
    case PackMLState::IDLE:
        idleState();
        break;
    case PackMLState::STARTING:
        startingState();
        break;
    case PackMLState::EXECUTE:
        break;
    case PackMLState::COMPLETING:
        completingState(uuidParam);
        break;
    case PackMLState::COMPLETE:
        transitionTo(PackMLState::RESETTING);
        break;
    case PackMLState::RESETTING:
        resettingState();
        break;
    case PackMLState::ABORTING:
        abortingState(uuidParam);
        break;
    case PackMLState::CLEARING:
        clearingState();
        break;
    default:
        break;
    }
}

void PackMLStateMachine::idleState()
{
    currentUuid = "";
    currentProcessingUuid = "";
    isProcessing = false;

    // Call virtual hook
    onIdle();

    if (!uuids.empty())
    {
        transitionTo(PackMLState::STARTING);
    }
}

void PackMLStateMachine::startingState()
{
    if (uuids.empty())
    {
        transitionTo(PackMLState::RESETTING);
        return;
    }

    currentUuid = uuids[0];

    // Check if this UUID has a pending registration and mark it as SUCCESS
    for (size_t i = 0; i < pendingRegistrations.size(); i++)
    {
        if (pendingRegistrations[i] == currentUuid)
        {
            publishCommandStatus(occupyDataTopic.c_str(), currentUuid, "SUCCESS");
            pendingRegistrations.erase(pendingRegistrations.begin() + i);
            break;
        }
    }

    transitionTo(PackMLState::EXECUTE);
}

void PackMLStateMachine::completingState(const String &uuidCompleted)
{
    // Call virtual hook
    onCompleting();

    if (uuidCompleted == "#")
    {
        // No specific UUID, just clean up
    }
    else
    {
        // Remove from queue
        for (size_t i = 0; i < uuids.size(); i++)
        {
            if (uuids[i] == uuidCompleted)
            {
                uuids.erase(uuids.begin() + i);
                break;
            }
        }
    }

    if (currentProcessingUuid == uuidCompleted)
    {
        currentProcessingUuid = "";
        isProcessing = false;
    }

    currentUuid = "";
    publishState();
    transitionTo(PackMLState::COMPLETE);
}

void PackMLStateMachine::abortingState(const String &abortedTaskUuid)
{
    Serial.print("Entering ABORTING state. Task: ");
    Serial.println(abortedTaskUuid.c_str());

    // Call virtual hook
    onAborting();

    // Fail all pending registrations
    for (const auto &uuid : pendingRegistrations)
    {
        publishCommandStatus(occupyDataTopic.c_str(), uuid, "FAILURE");
    }
    pendingRegistrations.clear();

    // Clear queue
    uuids.clear();
    currentUuid = "";
    currentProcessingUuid = "";
    isProcessing = false;

    publishState();
    transitionTo(PackMLState::ABORTED);
}

void PackMLStateMachine::resettingState()
{
    currentUuid = "";
    currentProcessingUuid = "";
    isProcessing = false;

    // Call virtual hook
    onResetting();

    transitionTo(PackMLState::IDLE);
}

void PackMLStateMachine::clearingState()
{
    uuids.clear();
    transitionTo(PackMLState::STOPPED);
}

// Helper methods
void PackMLStateMachine::publishState()
{
    JsonDocument doc;
    doc["State"] = stateToString(state);
    doc["TimeStamp"] = getTimestamp();

    JsonArray queueArray = doc["ProcessQueue"].to<JsonArray>();
    for (const auto &uuid : uuids)
    {
        queueArray.add(uuid);
    }

    char output[512];
    serializeJson(doc, output);
    client->publish(stateDataTopic.c_str(), output, true);
}

void PackMLStateMachine::publishCommandStatus(const String &topic, const String &uuid, const char *stateValue)
{
    JsonDocument doc;
    doc["State"] = stateValue;
    doc["TimeStamp"] = getTimestamp();
    doc["Uuid"] = uuid;

    char output[256];
    serializeJson(doc, output);
    client->publish(topic.c_str(), output, false);
}

String PackMLStateMachine::getTimestamp()
{
    struct tm timeinfo;
    if (!getLocalTime(&timeinfo))
    {
        return "2000-01-01T00:00:00.000Z";
    }

    char buffer[30];
    strftime(buffer, sizeof(buffer), "%Y-%m-%dT%H:%M:%S", &timeinfo);
    return String(buffer) + ".000Z";
}

String PackMLStateMachine::stateToString(PackMLState state)
{
    switch (state)
    {
    case PackMLState::IDLE:
        return "IDLE";
    case PackMLState::STARTING:
        return "STARTING";
    case PackMLState::EXECUTE:
        return "EXECUTE";
    case PackMLState::COMPLETING:
        return "COMPLETING";
    case PackMLState::COMPLETE:
        return "COMPLETE";
    case PackMLState::RESETTING:
        return "RESETTING";
    case PackMLState::HOLDING:
        return "HOLDING";
    case PackMLState::HELD:
        return "HELD";
    case PackMLState::UNHOLDING:
        return "UNHOLDING";
    case PackMLState::SUSPENDING:
        return "SUSPENDING";
    case PackMLState::SUSPENDED:
        return "SUSPENDED";
    case PackMLState::UNSUSPENDING:
        return "UNSUSPENDING";
    case PackMLState::STOPPING:
        return "STOPPING";
    case PackMLState::STOPPED:
        return "STOPPED";
    case PackMLState::ABORTING:
        return "ABORTING";
    case PackMLState::ABORTED:
        return "ABORTED";
    case PackMLState::CLEARING:
        return "CLEARING";
    default:
        return "UNKNOWN";
    }
}