#pragma once

#include "backends/action_backend.h"
#include "backends/mqtt/imqtt_subscriber.h"

#include <memory>
#include <mutex>
#include <optional>
#include <string>
#include <vector>

class IMqttClient;
class AASClient;
namespace jsonata
{
    class Jsonata;
}

/// Async MQTT action backend.  Parses the ActionContext in onStart(),
/// builds a JSONata message, publishes to the asset's MQTT input topic,
/// and waits for a UUID-correlated response on the output topic.
class MqttActionBackend : public IActionBackend
{
public:
    MqttActionBackend(IMqttClient &mqtt_client, AASClient &aas_client);
    ~MqttActionBackend() override;

    void initialize() override;
    BT::NodeStatus onStart(const ActionContext &ctx) override;
    BT::NodeStatus onRunning() override;
    void onHalted() override;
    nlohmann::json responseData() const override;
    bool isConfigured() const override { return true; }
    std::string backendName() const override { return "MQTT"; }

private:
    class ResponseHandler : public IMqttSubscriber
    {
    public:
        ResponseHandler(IMqttClient &c, MqttActionBackend &o) : IMqttSubscriber(c), owner_(o) {}
        void callback(const std::string &, const nlohmann::json &, mqtt::properties) override;
        std::string getBTNodeName() const override { return "MqttActionBackend"; }

    private:
        MqttActionBackend &owner_;
    };

    IMqttClient &mqtt_client_;
    AASClient &aas_client_;
    std::unique_ptr<ResponseHandler> response_handler_;

    mutable std::mutex mutex_;
    bool running_ = false;
    std::string output_topic_;
    std::string current_uuid_;
    nlohmann::json last_response_;
    std::optional<BT::NodeStatus> pending_terminal_;
};
