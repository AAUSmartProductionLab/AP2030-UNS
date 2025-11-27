#ifndef PACKML_STATE_MACHINE_H
#define PACKML_STATE_MACHINE_H

#include <Arduino.h>
#include <ArduinoJson.h>
#include <AsyncMqttClient.h>
#include <vector>
#include <time.h>

// PackML State Enumeration
enum class PackMLState
{
    IDLE,
    STARTING,
    EXECUTE,
    COMPLETING,
    COMPLETE,
    RESETTING,
    HOLDING,
    HELD,
    UNHOLDING,
    SUSPENDING,
    SUSPENDED,
    UNSUSPENDING,
    STOPPING,
    STOPPED,
    ABORTING,
    ABORTED,
    CLEARING
};

// Forward declaration for command callback
class PackMLStateMachine;
typedef void (*CommandCallback)(PackMLStateMachine *, const JsonDocument &);

// Command registration structure
struct CommandHandler
{
    String cmdTopic;
    String dataTopic;
    CommandCallback callback;
};

class PackMLStateMachine
{
private:
    PackMLState state;
    String baseTopic;
    String moduleName;
    AsyncMqttClient *client;

    // Process queue
    std::vector<String> uuids;
    std::vector<String> pendingRegistrations; // Maps queued UUID to original registration command UUID
    bool isProcessing;
    String currentProcessingUuid;
    String currentUuid;

    // Command handlers
    std::vector<CommandHandler> commandHandlers;
    bool subscriptionsInitialized;

    // Topics
    String occupyCmdTopic;
    String occupyDataTopic;
    String releaseCmdTopic;
    String releaseDataTopic;
    String stateDataTopic;

    // Helper methods
    void publishCommandStatus(const String &topic, const String &uuid, const char *stateValue);
    String stateToString(PackMLState state);

    // State transition methods
    void transitionTo(PackMLState newState, const String &uuidParam = "");
    void idleState();
    void startingState();
    void completingState(const String &uuidCompleted);
    void abortingState(const String &abortedTaskUuid);
    void resettingState();
    void clearingState();

protected:
    // Virtual hooks for derived classes to override
    virtual void onCompleting() {} // Called when entering COMPLETING state
    virtual void onResetting() {}  // Called when entering RESETTING state
    virtual void onAborting() {}   // Called when entering ABORTING state
    virtual void onIdle() {}       // Called when entering IDLE state

public:
    PackMLStateMachine(const String &baseTopic, const String &moduleName, AsyncMqttClient *mqttClient);
    virtual ~PackMLStateMachine() {}

    // Setup
    void setup();

    // Public methods that can be called by ESP32Module
    void subscribeToTopics();
    void publishState();
    String getTimestamp();

    // Command registration
    void registerCommandHandler(const String &cmdTopic, const String &dataTopic,
                                CommandCallback callback);

    // Message handling
    void handleMessage(const String &topic, const JsonDocument &message);

    // Command execution
    void executeCommand(const JsonDocument &message, const String &topic,
                        void (*processFunction)());
    void executeCommand(const JsonDocument &message, const String &topic,
                        bool (*processFunction)());

    // Queue management
    void occupyCommand(const String &uuid);
    void releaseCommand(const String &uuid);
    void abortCommand();

    // State queries
    PackMLState getState() const { return state; }
    String getCurrentUuid() const { return currentUuid; }
    bool isIdle() const { return state == PackMLState::IDLE; }

    // Callbacks for occupy/release
    static void occupyCallback(PackMLStateMachine *sm, const JsonDocument &message);
    static void releaseCallback(PackMLStateMachine *sm, const JsonDocument &message);
};

#endif // PACKML_STATE_MACHINE_H
