#pragma once

#include <nlohmann/json.hpp>
#include <nlohmann/json-schema.hpp>
#include <mutex>
#include <string>
#include <map>
#include "utils.h"

class IMqttClient;

namespace mqtt
{
    struct properties;
}

/// Minimal interface for objects that receive routed MQTT messages
/// through NodeMessageDistributor.  No static globals — backends
/// obtain the NMD and AAS interface cache from MqttInfra instead.
class IMqttSubscriber
{
protected:
    IMqttClient &mqtt_client_;
    std::map<std::string, mqtt_utils::Topic> topics_;

public:
    IMqttSubscriber(IMqttClient &mqtt_client) : mqtt_client_(mqtt_client) {}
    virtual ~IMqttSubscriber() = default;

    /// Topic-matching dispatch: iterates registered topics, validates
    /// against the JSON schema carried by each Topic, and calls
    /// callback() on the first match.
    void processMessage(const std::string &actual_topic_str,
                        const nlohmann::json &msg,
                        mqtt::properties props);

    void setTopic(const std::string &topic_key,
                  const mqtt_utils::Topic &topic_object);

    /// All topics registered by this subscriber.
    const std::map<std::string, mqtt_utils::Topic> &getTopics() const
    {
        return topics_;
    }

    /// Called by processMessage() when a registered topic matches.
    virtual void callback(const std::string &topic_key,
                          const nlohmann::json &msg,
                          mqtt::properties props) = 0;

    /// Type-name used by NMD for per-type subscription routing.
    virtual std::string getRegistrationName() const
    {
        return typeid(*this).name();
    }

    /// BT node name used by NMD to filter active-tree instances.
    virtual std::string getBTNodeName() const = 0;
};
