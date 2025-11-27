#include "PackMLStateMachine.h"

PackMLStateMachine::PackMLStateMachine(const String &baseTopic, const String &moduleName, AsyncMqttClient *mqttClient)
    : state(PackMLState::RESETTING), baseTopic(baseTopic), moduleName(moduleName), client(mqttClient),
      isProcessing(false), currentProcessingUuid(""), currentUuid(""), subscriptionsInitialized(false)
{
    occupyCmdTopic = baseTopic + "/" + moduleName + "/CMD/Occupy";
    occupyDataTopic = baseTopic + "/" + moduleName + "/DATA/Occupy";
    releaseCmdTopic = baseTopic + "/" + moduleName + "/CMD/Release";
    releaseDataTopic = baseTopic + "/" + moduleName + "/DATA/Release";
    stateDataTopic = baseTopic + "/" + moduleName + "/DATA/State";
    resettingState();
}

void PackMLStateMachine::subscribeToTopics()
{
    if (subscriptionsInitialized)
    {
        return; // Already subscribed
    }

    Serial.println("📡 Subscribing to MQTT topics...");

    // Subscribe to occupy and release topics
    uint16_t packetId1 = client->subscribe(occupyCmdTopic.c_str(), 0);
    Serial.print("  ✓ ");
    Serial.print(occupyCmdTopic);
    Serial.print(" (packetId: ");
    Serial.print(packetId1);
    Serial.println(")");

    uint16_t packetId2 = client->subscribe(releaseCmdTopic.c_str(), 0);
    Serial.print("  ✓ ");
    Serial.print(releaseCmdTopic);
    Serial.print(" (packetId: ");
    Serial.print(packetId2);
    Serial.println(")");

    // Subscribe to all registered command handler topics
    for (const auto &handler : commandHandlers)
    {
        uint16_t packetId = client->subscribe(handler.cmdTopic.c_str(), 0);
        Serial.print("  ✓ ");
        Serial.print(handler.cmdTopic);
        Serial.print(" (packetId: ");
        Serial.print(packetId);
        Serial.println(")");
    }

    subscriptionsInitialized = true;
    Serial.println("✅ All subscriptions complete\n");
}

void PackMLStateMachine::registerCommandHandler(const String &cmdTopic, const String &dataTopic,
                                                CommandCallback callback)
{
    CommandHandler handler;
    handler.cmdTopic = baseTopic + "/" + moduleName + cmdTopic;
    handler.dataTopic = baseTopic + "/" + moduleName + dataTopic;
    handler.callback = callback;
    commandHandlers.push_back(handler);

    Serial.print("Registered: ");
    Serial.println(handler.cmdTopic);
}

void PackMLStateMachine::handleMessage(const String &topic, const JsonDocument &message)
{
    // Check if it's an occupy/release command
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
    String commandUuid = message["Uuid"].as<String>();
    String topic = baseTopic + "/" + moduleName + dataTopic;

    // Condition 1: Not in EXECUTE state
    if (state != PackMLState::EXECUTE)
    {
        Serial.print("Execute command rejected for UUID '");
        Serial.print(commandUuid);
        Serial.print("'. Machine not in EXECUTE state (current: ");
        Serial.print(stateToString(state).c_str());
        Serial.println(").");

        publishCommandStatus(topic, commandUuid, "FAILURE");
        return;
    }

    // Condition 2: Queue is empty
    if (uuids.empty())
    {
        Serial.print("Execute command rejected for UUID '");
        Serial.print(commandUuid);
        Serial.println("'. Queue is empty.");

        publishCommandStatus(topic, commandUuid, "FAILURE");
        return;
    }

    // Condition 3: UUID not at front of queue
    if (uuids[0] != commandUuid)
    {
        Serial.print("Execute command rejected for UUID '");
        Serial.print(commandUuid);
        Serial.print("'. Expected head: '");
        Serial.print(uuids[0]);
        Serial.print("', Queue: [");
        for (size_t i = 0; i < uuids.size(); i++)
        {
            Serial.print(uuids[i]);
            if (i < uuids.size() - 1)
                Serial.print(", ");
        }
        Serial.println("]");

        publishCommandStatus(topic, commandUuid, "FAILURE");
        return;
    }

    // Condition 4: Already processing another command
    if (isProcessing)
    {
        Serial.print("Execute command rejected for UUID '");
        Serial.print(commandUuid);
        Serial.print("'. Already processing: ");
        Serial.println(currentProcessingUuid);

        publishCommandStatus(topic, commandUuid, "FAILURE");
        return;
    }

    // All conditions met - execute the command
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

void PackMLStateMachine::executeCommand(const JsonDocument &message, const String &dataTopic,
                                        bool (*processFunction)())
{
    String commandUuid = message["Uuid"].as<String>();
    String topic = baseTopic + "/" + moduleName + dataTopic;

    // Condition 1: Not in EXECUTE state
    if (state != PackMLState::EXECUTE)
    {
        Serial.print("Execute command rejected for UUID '");
        Serial.print(commandUuid);
        Serial.print("'. Machine not in EXECUTE state (current: ");
        Serial.print(stateToString(state).c_str());
        Serial.println(").");

        publishCommandStatus(topic, commandUuid, "FAILURE");
        return;
    }

    // Condition 2: Queue is empty
    if (uuids.empty())
    {
        Serial.print("Execute command rejected for UUID '");
        Serial.print(commandUuid);
        Serial.println("'. Queue is empty.");

        publishCommandStatus(topic, commandUuid, "FAILURE");
        return;
    }

    // Condition 3: UUID not at front of queue
    if (uuids[0] != commandUuid)
    {
        Serial.print("Execute command rejected for UUID '");
        Serial.print(commandUuid);
        Serial.print("'. Expected head: '");
        Serial.print(uuids[0]);
        Serial.print("', Queue: [");
        for (size_t i = 0; i < uuids.size(); i++)
        {
            Serial.print(uuids[i]);
            if (i < uuids.size() - 1)
                Serial.print(", ");
        }
        Serial.println("]");

        publishCommandStatus(topic, commandUuid, "FAILURE");
        return;
    }

    // Condition 4: Already processing another command
    if (isProcessing)
    {
        Serial.print("Execute command rejected for UUID '");
        Serial.print(commandUuid);
        Serial.print("'. Already processing: ");
        Serial.println(currentProcessingUuid);

        publishCommandStatus(topic, commandUuid, "FAILURE");
        return;
    }

    // All conditions met - execute the command
    isProcessing = true;
    currentProcessingUuid = commandUuid;

    // Publish RUNNING status
    publishCommandStatus(topic, commandUuid, "RUNNING");

    // Execute the process function and check result
    bool success = true;
    if (processFunction)
    {
        success = processFunction();
    }

    // Mark completion with appropriate status
    if (success)
    {
        publishCommandStatus(topic, commandUuid, "SUCCESS");
    }
    else
    {
        publishCommandStatus(topic, commandUuid, "FAILURE");
    }

    isProcessing = false;
    currentProcessingUuid = "";

    // // Transition to completing state
    // transitionTo(PackMLState::COMPLETING, commandUuid);
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
    size_t len = serializeJson(doc, output);
    client->publish(stateDataTopic.c_str(), 2, true, output, len);
}

void PackMLStateMachine::publishCommandStatus(const String &topic, const String &uuid, const char *stateValue)
{
    JsonDocument doc;
    doc["State"] = stateValue;
    doc["TimeStamp"] = getTimestamp();
    doc["Uuid"] = uuid;

    char output[256];
    size_t len = serializeJson(doc, output);
    client->publish(topic.c_str(), 2, true, output, len);
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