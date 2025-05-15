#pragma once

#include <mqtt/async_client.h> // Paho MQTT C++ library
#include <nlohmann/json.hpp>   // For JSON handling

#include <functional> // For std::function
#include <memory>     // For std::unique_ptr, std::make_unique (though not directly used here)
#include <string>
#include <vector>
#include <iostream>  // For std::cout, std::cerr (mainly in .cpp)
#include <algorithm> // For std::find_if, std::remove_if

using json = nlohmann::json;

class MqttClient : public mqtt::async_client, public virtual mqtt::callback // Ensure virtual inheritance for callback
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
    // connected() and connection_lost() are also part of mqtt::callback
    // but Paho async_client provides set_connected_handler and set_disconnected_handler
    // which are often more convenient.

    // --- Topic Subscription Management ---
    bool subscribe_topic(const std::string &topic, int qos);
    bool unsubscribe_topic(const std::string &topic);
    void resubscribe_all_topics(); // Typically called on reconnect

    // --- Message Handling ---
    void set_message_handler(MessageCallback handler) { message_handler_ = std::move(handler); }

    // --- Publishing ---
    bool publish_message(const std::string &topic, const json &payload,
                         int qos, bool retained = false);

    // --- Connection Status ---
    // is_connected() is inherited from mqtt::async_client
    // void disconnect(); // Consider adding an explicit disconnect method if needed beyond destructor

private:
    // --- Action Listener for Subscribe Operations ---
    class subscription_listener : public virtual mqtt::iaction_listener
    {
    private:
        std::string topic_;
        // MqttClient& client_; // If needed for more complex actions on callback

        void on_failure(const mqtt::token &tok) override;
        void on_success(const mqtt::token &tok) override;

    public:
        explicit subscription_listener(const std::string &topic /*, MqttClient& client*/)
            : topic_(topic) /*, client_(client)*/ {}
    };

    // --- Action Listener for Unsubscribe Operations ---
    class unsubscription_listener : public virtual mqtt::iaction_listener
    {
    private:
        std::string topic_;
        // MqttClient& client_;

        void on_failure(const mqtt::token &tok) override;
        void on_success(const mqtt::token &tok) override;

    public:
        explicit unsubscription_listener(const std::string &topic /*, MqttClient& client*/)
            : topic_(topic) /*, client_(client)*/ {}
    };

    std::string server_uri_;
    mqtt::connect_options conn_opts_;
    int nretry_attempts_; // Renamed for clarity
    MessageCallback message_handler_ = nullptr;

    struct TopicSubscriptionInfo
    {
        std::string topic;
        int qos;
    };
    std::vector<TopicSubscriptionInfo> tracked_subscriptions_; // Tracks desired subscriptions

    // --- Internal Connection Handlers ---
    void on_successful_connect(); // Called by Paho's connected_handler
    void on_connection_failure(); // Called by Paho's disconnected_handler or connection_lost
    // void attempt_manual_reconnect(); // Manual reconnect logic, potentially redundant if Paho's auto-reconnect is used
};
