#pragma once

#include <nlohmann/json.hpp>
#include <nlohmann/json-schema.hpp>
#include <mutex>
#include <string>
#include <functional>
#include <map>
#include "utils.h"

// Forward declarations
namespace BT
{
    class BehaviorTreeFactory;
}

class MqttClient;
class NodeMessageDistributor;
class AASInterfaceCache;

namespace mqtt
{
    struct properties;
}

using json_uri = nlohmann::json_uri;

class MqttSubBase
{
protected:
    MqttClient &mqtt_client_;
    std::mutex mutex_;
    static NodeMessageDistributor *node_message_distributor_;
    static AASInterfaceCache *aas_interface_cache_;

public:
    MqttSubBase(MqttClient &mqtt_client);

    virtual ~MqttSubBase() = default;

    void processMessage(const std::string &actual_topic_str, const nlohmann::json &msg, mqtt::properties props);
    void setTopic(const std::string &topic_key, const mqtt_utils::Topic &topic_object);
    virtual void callback(const std::string &topic_key, const nlohmann::json &msg, mqtt::properties props) = 0;

    // Get all configured topics for this node
    const std::map<std::string, mqtt_utils::Topic>& getTopics() const { return topics_; }

    static void setNodeMessageDistributor(NodeMessageDistributor *manager);
    static void setAASInterfaceCache(AASInterfaceCache *cache);
    static AASInterfaceCache* getAASInterfaceCache();

    virtual std::string getRegistrationName() const
    {
        return typeid(*this).name();
    }
    virtual std::string getBTNodeName() const = 0;

    std::map<std::string, mqtt_utils::Topic> topics_;
};