#pragma once

#include "backends/condition_backend.h"
#include "backends/aas/transformation_resolver.h"
#include "backends/mqtt/imqtt_subscriber.h"

#include <memory>
#include <string>
#include <vector>

class IMqttClient;
class AASClient;
class TransformationResolver;
namespace bt_exec_refs
{
    struct PredicateRef;
}
namespace jsonata
{
    class Jsonata;
}

/// MQTT-backed condition backend.  Subscribes to the asset's MQTT data
/// topics and evaluates a JSONata transformation against the latest
/// received message.
///
/// Internally uses a small IMqttSubscriber-derived helper for message routing
/// through the existing NodeMessageDistributor infrastructure.
class MqttConditionBackend : public IConditionBackend
{
public:
    MqttConditionBackend(IMqttClient &mqtt_client,
                         AASClient &aas_client);

    ~MqttConditionBackend() override;

    void initialize() override;
    std::optional<bool> evaluate(const std::string &predicate_name,
                                 const std::vector<std::string> &args) override;
    bool isConfigured() const override;
    std::string backendName() const override { return "MQTT"; }

    /// Initialize topics and JSONata (called once, lazy).
    bool initializeTopics();

    /// Seed the latest message from an AAS pre-fetch.
    void seedInitialValue(const nlohmann::json &msg);

private:
    class DataHandler : public IMqttSubscriber
    {
    public:
        DataHandler(IMqttClient &mqtt_client, MqttConditionBackend &owner);
        void callback(const std::string &topic_key,
                      const nlohmann::json &msg,
                      mqtt::properties props) override;
        std::string getBTNodeName() const override { return "MqttConditionBackend"; }

    private:
        MqttConditionBackend &owner_;
    };

    IMqttClient &mqtt_client_;
    AASClient &aas_client_;

    std::shared_ptr<TransformationResolver> transformation_resolver_;
    std::unique_ptr<jsonata::Jsonata> jsonata_expr_;
    std::string transformation_expression_;
    nlohmann::json constants_;
    std::vector<nlohmann::json> param_snapshots_;
    nlohmann::json latest_msg_;
    bool topics_initialized_ = false;

    std::unique_ptr<DataHandler> data_handler_;
};
