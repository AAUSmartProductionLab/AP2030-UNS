#pragma once
#include <mqtt/async_client.h>
#include <nlohmann/json.hpp>
#include <functional>
#include <memory>
#include <string>
#include <vector>
#include <iostream>

using nlohmann::json;

// Forward declaration
class NodeMessageDistributor;

class MqttClient : public mqtt::async_client, public mqtt::callback
{
public:
    using MessageCallback = std::function<void(const std::string &, const json &, mqtt::properties)>;

    MqttClient(std::string serverURI, std::string client_id,
               mqtt::connect_options connOpts, int nretry);
    virtual ~MqttClient() override;

    // MQTT callback interface implementation
    void message_arrived(mqtt::const_message_ptr msg) override;
    void connection_lost(const std::string &cause) override;
    void delivery_complete(mqtt::delivery_token_ptr token) override;

    // Topic subscription management
    bool subscribe_topic(const std::string &topic, int subqos);
    void resubscribe_all_topics();

    // Set message handler
    void set_message_handler(MessageCallback handler) { message_handler_ = handler; }

    // Publishing interface
    bool publish_message(const std::string &topic, const json &payload,
                         int pubqos, bool retained = false);

private:
    // Nested class for subscription status events
    class subscription_listener : public virtual mqtt::iaction_listener
    {
    private:
        std::string topic_;
        MqttClient &client_;

        void on_failure(const mqtt::token &tok) override;
        void on_success(const mqtt::token &tok) override;

    public:
        subscription_listener(const std::string &topic, MqttClient &client)
            : topic_(topic), client_(client) {}
    };

    std::string server_uri_;
    mqtt::connect_options conn_opts_;
    int nretry_;
    MessageCallback message_handler_ = nullptr;

    struct TopicSubscription
    {
        std::string topic;
        int subqos;
    };
    std::vector<TopicSubscription> subscriptions_;

    void on_connect();
    void on_disconnect();
    void attempt_reconnect();
};
