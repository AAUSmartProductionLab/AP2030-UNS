#include "mqtt/mqtt_client.h"
// #include "mqtt/node_message_distributor.h" // Not directly needed here

#include <iostream>
#include <chrono>    // For std::chrono::seconds
#include <thread>    // For std::this_thread::sleep_for (if manual reconnect used)
#include <algorithm> // For std::find_if, std::remove_if

MqttClient::MqttClient(std::string serverURI, std::string client_id,
                       mqtt::connect_options connOpts, int nretry_attempts)
    : mqtt::async_client(serverURI, client_id), // Initialize base
      server_uri_(std::move(serverURI)),
      conn_opts_(std::move(connOpts)),
      nretry_attempts_(nretry_attempts)
{

    set_callback(*this);

    set_connected_handler([this](const std::string &cause)
                          { this->on_successful_connect(); });

    set_disconnected_handler([this](const mqtt::properties &props, mqtt::ReasonCode reason)
                             {
                                 std::string cause_str = "Disconnected. Reason: " + mqtt::exception::reason_code_str(reason);
                                 if (!props.empty())
                                 {
                                     // Log properties if any
                                 }
                                 this->connection_lost(cause_str); });

    try
    {
        std::cout << "Attempting to connect to MQTT broker: " << server_uri_ << " with client ID: " << client_id << std::endl;
        connect(conn_opts_)->wait_for(std::chrono::seconds(10));
    }
    catch (const mqtt::exception &exc)
    {
        std::cerr << "Initial connection failed: " << exc.what() << std::endl;
    }
}

MqttClient::~MqttClient()
{
    if (is_connected())
    {
        std::cout << "Disconnecting MQTT client in destructor..." << std::endl;
        try
        {
            disconnect(std::chrono::seconds(5))->wait();
        }
        catch (const mqtt::exception &exc)
        {
            std::cerr << "Exception during MQTT disconnect: " << exc.what() << std::endl;
        }
    }
}

void MqttClient::message_arrived(mqtt::const_message_ptr msg)
{
    std::string topic = msg->get_topic();
    try
    {
        json payload = json::parse(msg->get_payload_str());

        if (message_handler_)
        {
            message_handler_(topic, payload, msg->get_properties());
        }
        else
        {
            // This can be verbose if many unhandled topics are expected (e.g. from wildcards)
            // std::cout << "Message arrived on topic '" << topic << "' but no application handler is set." << std::endl;
        }
    }
    catch (const json::parse_error &e)
    {
        std::cerr << "JSON parse error for message on topic '" << topic << "': " << e.what()
                  << "\nPayload: " << msg->get_payload_str() << std::endl;
    }
    catch (const std::exception &e)
    {
        std::cerr << "Error processing message on topic '" << topic << "': " << e.what() << std::endl;
    }
}

void MqttClient::connection_lost(const std::string &cause)
{
    std::cout << "MQTT connection lost.";
    if (!cause.empty())
    {
        std::cout << " Cause: " << cause << std::endl;
    }
    on_connection_failure(); // Call internal handler
}

void MqttClient::delivery_complete(mqtt::delivery_token_ptr token)
{
    // Optional: Log if token is not null and message ID is relevant
    // if (token) {
    //     std::cout << "Delivery complete for token: " << token->get_message_id() << std::endl;
    // }
}

bool MqttClient::subscribe_topic(const std::string &topic, int qos)
{
    if (!is_connected())
    {
        std::cerr << "Cannot subscribe to topic '" << topic << "', MQTT client not connected." << std::endl;
        // Add to tracked_subscriptions_ anyway, so on_successful_connect can pick it up
        if (std::find_if(tracked_subscriptions_.begin(), tracked_subscriptions_.end(),
                         [&](const TopicSubscriptionInfo &tsi)
                         { return tsi.topic == topic; }) == tracked_subscriptions_.end())
        {
            tracked_subscriptions_.push_back({topic, qos});
        }
        return false;
    }

    auto it = std::find_if(tracked_subscriptions_.begin(), tracked_subscriptions_.end(),
                           [&](const TopicSubscriptionInfo &sub)
                           { return sub.topic == topic; });

    if (it == tracked_subscriptions_.end())
    { // Not in our tracking list yet
        tracked_subscriptions_.push_back({topic, qos});
    }
    else if (it->qos != qos)
    {
        it->qos = qos;
        std::cout << "QoS for tracked subscription '" << topic << "' updated to " << qos << ". Re-subscription needed to apply." << std::endl;
    }

    try
    {
        auto listener = new subscription_listener(topic);
        subscribe(topic, qos, nullptr, *listener);
        return true;
    }
    catch (const mqtt::exception &exc)
    {
        std::cerr << "Subscription to topic '" << topic << "' failed: " << exc.what() << std::endl;
        return false;
    }
}

bool MqttClient::unsubscribe_topic(const std::string &topic)
{
    tracked_subscriptions_.erase(
        std::remove_if(tracked_subscriptions_.begin(), tracked_subscriptions_.end(),
                       [&](const TopicSubscriptionInfo &sub)
                       { return sub.topic == topic; }),
        tracked_subscriptions_.end());

    if (!is_connected())
    {
        std::cerr << "Cannot unsubscribe from topic '" << topic << "', MQTT client not connected (removed from tracking)." << std::endl;
        return false; // Not connected, but removed from our list
    }

    try
    {
        auto listener = new unsubscription_listener(topic);
        unsubscribe(topic, nullptr, *listener);
        return true;
    }
    catch (const mqtt::exception &exc)
    {
        std::cerr << "Unsubscription from topic '" << topic << "' failed: " << exc.what() << std::endl;
        return false;
    }
}

void MqttClient::resubscribe_all_topics()
{
    if (!is_connected())
    {
        return;
    }
    if (tracked_subscriptions_.empty())
    {
        return;
    }

    std::vector<TopicSubscriptionInfo> current_subs = tracked_subscriptions_;

    for (const auto &sub_info : current_subs)
    {
        try
        {
            auto listener = new subscription_listener(sub_info.topic);
            subscribe(sub_info.topic, sub_info.qos, nullptr, *listener);
        }
        catch (const mqtt::exception &exc)
        {
            std::cerr << "Failed to resubscribe to topic '" << sub_info.topic << "': " << exc.what() << std::endl;
        }
    }
}

// --- Publishing ---

bool MqttClient::publish_message(const std::string &topic, const json &payload,
                                 int qos, bool retained)
{
    if (!is_connected())
    {
        std::cerr << "Cannot publish to topic '" << topic << "', MQTT client not connected." << std::endl;
        return false;
    }

    try
    {
        std::string payload_str = payload.dump();
        auto msg = mqtt::make_message(topic, payload_str);
        msg->set_qos(qos);
        msg->set_retained(retained);
        publish(msg);
        return true;
    }
    catch (const mqtt::exception &exc)
    {
        std::cerr << "Publication to topic '" << topic << "' failed: " << exc.what() << std::endl;
        return false;
    }
}

// --- Internal Connection Handlers ---

void MqttClient::on_successful_connect()
{
    std::cout << "Successfully connected to MQTT broker: " << server_uri_ << std::endl;
    resubscribe_all_topics();
}

void MqttClient::on_connection_failure()
{
    std::cout << "MQTT connection failure processing." << std::endl;
}

// --- Listener Implementations ---

void MqttClient::subscription_listener::on_failure(const mqtt::token &tok)
{
}

void MqttClient::subscription_listener::on_success(const mqtt::token &tok)
{
}

void MqttClient::unsubscription_listener::on_failure(const mqtt::token &tok)
{
}

void MqttClient::unsubscription_listener::on_success(const mqtt::token &tok)
{
}
