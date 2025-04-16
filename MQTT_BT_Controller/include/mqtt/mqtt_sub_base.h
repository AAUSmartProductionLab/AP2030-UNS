#pragma once

#include <nlohmann/json.hpp>
#include <nlohmann/json-schema.hpp>
#include <mutex>
#include <string>
#include <functional>

// Forward declarations
namespace BT
{
    class BehaviorTreeFactory;
}

class MqttClient;
class NodeMessageDistributor;

namespace mqtt
{
    struct properties;
}

using json = nlohmann::json;
using json_uri = nlohmann::json_uri;

class MqttSubBase
{
protected:
    MqttClient &mqtt_client_;
    std::string response_topic_;
    std::string response_schema_path_;
    std::mutex mutex_;

    std::unique_ptr<nlohmann::json_schema::json_validator> response_schema_validator_;
    static NodeMessageDistributor *node_message_distributor_;

public:
    MqttSubBase(MqttClient &mqtt_client,
                const std::string &response_topic,
                const std::string &response_schema_path);

    virtual ~MqttSubBase() = default;

    void handleMessage(const json &msg, mqtt::properties props);

    virtual bool isInterestedIn(const json &msg);

    virtual void callback(const json &msg, mqtt::properties props) = 0;

    static void setNodeMessageDistributor(NodeMessageDistributor *manager);
};