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

// ═══════════════════════════════════════════════════════════════════════
// Abstract MQTT client interface — decouples all BT nodes and the
// controller from the concrete Paho library.
// ═══════════════════════════════════════════════════════════════════════

class IMqttClient
{
public:
    using MessageCallback = std::function<void(const std::string &topic,
                                               const json &payload,
                                               mqtt::properties props)>;

    virtual ~IMqttClient() = default;

    /// Subscribe to a topic. Returns true if the subscription was
    /// successfully initiated.
    virtual bool subscribe_topic(const std::string &topic, int qos) = 0;

    /// Unsubscribe from a topic. Returns true on success.
    virtual bool unsubscribe_topic(const std::string &topic) = 0;

    /// Publish a JSON payload to a topic.
    virtual bool publish_message(const std::string &topic,
                                 const json &payload,
                                 int qos,
                                 bool retained = false) = 0;

    /// Publish an arbitrary string payload to a topic.
    virtual bool publish_message_raw(const std::string &topic,
                                     const std::string &payload,
                                     int qos,
                                     bool retained = false) = 0;

    /// Check whether the client is connected to the broker.
    virtual bool is_connected() const = 0;

    /// Register the global incoming-message handler.
    virtual void set_message_handler(MessageCallback handler) = 0;

    /// Low-level Paho subscribe returning the token (used by
    /// NodeMessageDistributor for retained-message timing).
    virtual mqtt::token_ptr subscribe_topic_paho(const std::string &topic,
                                                 int qos) = 0;
};

// ═══════════════════════════════════════════════════════════════════════
// Concrete IMqttClient backed by the Eclipse Paho C++ library.
// ═══════════════════════════════════════════════════════════════════════

class PahoMqttClient : public IMqttClient,
                       public mqtt::async_client,
                       public virtual mqtt::callback
{
public:
    PahoMqttClient(std::string serverURI, std::string client_id,
                   mqtt::connect_options connOpts, int nretry_attempts);
    ~PahoMqttClient() override;

    // --- mqtt::callback overrides ---
    void message_arrived(mqtt::const_message_ptr msg) override;
    void connection_lost(const std::string &cause) override;
    void delivery_complete(mqtt::delivery_token_ptr token) override;

    // --- IMqttClient overrides ---
    bool subscribe_topic(const std::string &topic, int qos) override;
    bool unsubscribe_topic(const std::string &topic) override;
    bool publish_message(const std::string &topic, const json &payload,
                         int qos, bool retained = false) override;
    bool publish_message_raw(const std::string &topic, const std::string &payload,
                             int qos, bool retained = false) override;
    bool is_connected() const override;
    void set_message_handler(MessageCallback handler) override;

    /// Re-subscribe all previously tracked topics (used on reconnect).
    void resubscribe_all_topics();

    /// Low-level subscribe that returns the Paho token (used by
    /// NodeMessageDistributor for retained-message delivery timing).
    mqtt::token_ptr subscribe_topic_paho(const std::string &topic, int qos);

private:
    class subscription_listener : public virtual mqtt::iaction_listener
    {
        std::string topic_;
        void on_failure(const mqtt::token &tok) override;
        void on_success(const mqtt::token &tok) override;

    public:
        explicit subscription_listener(const std::string &topic) : topic_(topic) {}
    };

    class unsubscription_listener : public virtual mqtt::iaction_listener
    {
        std::string topic_;
        void on_failure(const mqtt::token &tok) override;
        void on_success(const mqtt::token &tok) override;

    public:
        explicit unsubscription_listener(const std::string &topic) : topic_(topic) {}
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

    void on_successful_connect();
    void on_connection_failure();
};

// ── Backward-compatibility alias ──────────────────────────────────────
// Code that hasn't been migrated yet can still use the old name.
using MqttClient = PahoMqttClient;
