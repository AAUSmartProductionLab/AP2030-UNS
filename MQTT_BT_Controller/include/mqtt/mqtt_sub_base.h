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

class Proxy;
class SubscriptionManager;

namespace mqtt
{
    struct properties;
}

using json = nlohmann::json;
using json_uri = nlohmann::json_uri;

class MqttSubBase
{
protected:
    Proxy &proxy_;
    std::string response_topic_;
    std::string response_schema_path_;
    std::mutex mutex_;

    std::unique_ptr<nlohmann::json_schema::json_validator> schema_validator_;
    static SubscriptionManager *subscription_manager_;

public:
    MqttSubBase(Proxy &proxy,
                const std::string &response_topic,
                const std::string &response_schema_path);

    virtual ~MqttSubBase() = default;

    void handleMessage(const json &msg, mqtt::properties props);

    virtual bool isInterestedIn(const std::string &field, const json &value);

    virtual void callback(const json &msg, mqtt::properties props) = 0;

    static void setSubscriptionManager(SubscriptionManager *manager);
};