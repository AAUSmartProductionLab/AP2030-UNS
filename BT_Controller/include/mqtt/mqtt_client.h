#pragma once

#include <mqtt/async_client.h>
#include <nlohmann/json.hpp>

#include <functional>
#include <memory>
#include <string>
#include <vector>
#include <iostream>
#include <algorithm>
using json = nlohmann::json;

class MqttClient : public mqtt::async_client, public virtual mqtt::callback
{
public:
    using MessageCallback = std::function<void(const std::string &topic, const json &payload, mqtt::properties props)>;

    MqttClient(std::string serverURI, std::string client_id,
               mqtt::connect_options connOpts, int nretry_attempts);
    virtual ~MqttClient() override;

    // --- MQTT Callback Interface (from mqtt::callback) ---
    void message_arrived(mqtt::const_message_ptr msg) override;
    void connection_lost(const std::string &cause) override;
    void delivery_complete(mqtt::delivery_token_ptr token) override;

    // --- Topic Subscription Management ---
    bool subscribe_topic(const std::string &topic, int qos);
    bool unsubscribe_topic(const std::string &topic);
    void resubscribe_all_topics();

    // --- Message Handling ---
    void set_message_handler(MessageCallback handler) { message_handler_ = std::move(handler); }

    // --- Publishing ---
    bool publish_message(const std::string &topic, const json &payload,
                         int qos, bool retained = false);

private:
    // --- Action Listener for Subscribe Operations ---
    class subscription_listener : public virtual mqtt::iaction_listener
    {
    private:
        std::string topic_;

        void on_failure(const mqtt::token &tok) override;
        void on_success(const mqtt::token &tok) override;

    public:
        explicit subscription_listener(const std::string &topic)
            : topic_(topic) {}
    };

    // --- Action Listener for Unsubscribe Operations ---
    class unsubscription_listener : public virtual mqtt::iaction_listener
    {
    private:
        std::string topic_;

        void on_failure(const mqtt::token &tok) override;
        void on_success(const mqtt::token &tok) override;

    public:
        explicit unsubscription_listener(const std::string &topic)
            : topic_(topic) {}
    };

    std::string server_uri_;
    mqtt::connect_options conn_opts_;
    int nretry_attempts_;
    MessageCallback message_handler_ = nullptr;

    struct TopicSubscriptionInfo
    {
        std::string topic;
        int qos;
    };
    std::vector<TopicSubscriptionInfo> tracked_subscriptions_;

    // --- Internal Connection Handlers ---
    void on_successful_connect();
    void on_connection_failure();
};
