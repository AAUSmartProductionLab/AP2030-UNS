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
    std::string response_schema_path_;

    std::mutex mutex_;

    std::unique_ptr<nlohmann::json_schema::json_validator> response_schema_validator_;
    // The response_topic that may include wildcards
    static NodeMessageDistributor *node_message_distributor_;

public:
    MqttSubBase(MqttClient &mqtt_client,
                const std::string &response_topic,
                const std::string &response_schema_path,
                const int &subqos);

    virtual ~MqttSubBase() = default;

    void processMessage(const json &msg, mqtt::properties props);

    virtual bool isInterestedIn(const json &msg);

    virtual void callback(const json &msg, mqtt::properties props) = 0;

    static void setNodeMessageDistributor(NodeMessageDistributor *manager);

    const std::string &getResponseTopic() const
    {
        return response_topic_;
    }
    virtual std::string getRegistrationName() const
    {
        // Default implementation - derived classes can override this
        return typeid(*this).name();
    }
    virtual std::string getBTNodeName() const = 0;
    const std::string response_topic_pattern_;
    std::string response_topic_; // The precise response_topic the node is interested in without wildcards
    int subqos_;
};