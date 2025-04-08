#pragma once
#include <mqtt/async_client.h>
#include <nlohmann/json.hpp>
#include <functional>
#include <memory>
#include <string>

using nlohmann::json;

// Forward declaration
class SubscriptionManager;

class Proxy : public mqtt::async_client
{
private:
    std::string address;
    mqtt::connect_options connOpts_;
    int nretry_;
    mqtt::callback *callback_ = nullptr;

    void on_connect();
    void on_disconnect();
    void on_connection_lost(const std::string &cause);
    void attempt_reconnect();

public:
    Proxy(std::string serverURI, std::string client_id,
          mqtt::connect_options connOpts, int nretry);

    void set_callback(mqtt::callback &callback)
    {
        callback_ = &callback;
        mqtt::async_client::set_callback(callback);
    }

    void register_topic_handler(const std::string &topic,
                                std::function<void(const json &, mqtt::properties)> callback);

    void subscribe_with_listener(const std::string &topic, int qos,
                                 void *context,
                                 std::shared_ptr<mqtt::iaction_listener> listener)
    {
        mqtt::async_client::subscribe(topic, qos, context, *listener)->wait();
    }
};