#pragma once

#include <nlohmann/json.hpp>
#include <mqtt/async_client.h>

using json = nlohmann::json;

/**
 * @brief Interface for classes that want to receive MQTT messages through the subscription manager
 */
class SubscriptionManagerClient
{
public:
    virtual ~SubscriptionManagerClient() = default;

    // Called when a message arrives
    virtual void handleMessage(const json &msg, mqtt::properties props) = 0;

    // Check if this node is interested in a message
    virtual bool isInterestedIn(const std::string &field, const json &value) = 0;
};