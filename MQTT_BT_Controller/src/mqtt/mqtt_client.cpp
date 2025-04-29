#include "mqtt/mqtt_client.h"
#include "mqtt/node_message_distributor.h"
#include <iostream>
#include <chrono>

MqttClient::MqttClient(std::string serverURI, std::string client_id,
                       mqtt::connect_options connOpts, int nretry)
    : mqtt::async_client(serverURI, client_id),
      server_uri_(serverURI), conn_opts_(connOpts), nretry_(nretry)
{

    conn_opts_.set_keep_alive_interval(20);

    // Add automatic reconnect properties
    conn_opts_.set_automatic_reconnect(true);
    conn_opts_.set_automatic_reconnect(2, 10); // Min and max reconnect delay in seconds

    // Set timeout for operations
    conn_opts_.set_connect_timeout(5);
    set_callback(*this);

    set_connected_handler([this](const std::string &)
                          { on_connect(); });

    set_disconnected_handler([this](const mqtt::properties &, mqtt::ReasonCode)
                             { on_disconnect(); });

    try
    {
        connect(conn_opts_)->wait();
    }
    catch (const mqtt::exception &exc)
    {
        std::cerr << "Connection failed: " << exc.what() << std::endl;
        // Don't exit - let client handle reconnection if desired
    }
}

MqttClient::~MqttClient()
{
    // Clean disconnect if still connected
    if (is_connected())
    {
        try
        {
            disconnect()->wait();
        }
        catch (...)
        {
            // Best effort
        }
    }
}

void MqttClient::message_arrived(mqtt::const_message_ptr msg)
{
    std::string topic = msg->get_topic();

    try
    {
        json payload = json::parse(msg->get_payload());
        mqtt::properties props = msg->get_properties();

        // Forward to message handler if set
        if (message_handler_)
        {
            message_handler_(topic, payload, props);
        }
        else
        {
            std::cout << "Message received on topic " << topic << " but no handler set" << std::endl;
        }
    }
    catch (const std::exception &e)
    {
        std::cerr << "Error processing message on topic " << topic << ": " << e.what() << std::endl;
    }
}

void MqttClient::connection_lost(const std::string &cause)
{
    std::cout << "Connection lost";
    if (!cause.empty())
    {
        std::cout << ", cause: " << cause;
    }
    std::cout << std::endl;

    // Attempt reconnection
    attempt_reconnect();
}

void MqttClient::delivery_complete(mqtt::delivery_token_ptr token)
{
    // Implementation can be empty if not needed
}

bool MqttClient::subscribe_topic(const std::string &topic, int subqos)
{
    if (!is_connected())
    {
        std::cerr << "Cannot subscribe, not connected" << std::endl;
        return false;
    }

    // Check if we already have a subscription for this topic
    auto it = std::find_if(subscriptions_.begin(), subscriptions_.end(),
                           [&topic](const TopicSubscription &sub)
                           {
                               return sub.topic == topic;
                           });

    // If subscription already exists, return true without resubscribing
    if (it != subscriptions_.end())
    {
        return true;
    }

    try
    {
        auto listener = new subscription_listener(topic, *this);
        subscribe(topic, subqos, nullptr, *listener);
        // Asynchronously subscribe to the topic
        subscriptions_.push_back({topic, subqos});
        return true;
    }
    catch (const mqtt::exception &exc)
    {
        std::cerr << "Subscription failed: " << exc.what() << std::endl;
        return false;
    }
}

void MqttClient::resubscribe_all_topics()
{
    if (!is_connected())
    {
        std::cerr << "Cannot resubscribe, not connected" << std::endl;
        return;
    }

    for (const auto &subscription : subscriptions_)
    {
        try
        {
            std::cout << "Resubscribing to: " << subscription.topic << std::endl;
            subscribe(subscription.topic, subscription.subqos)->wait();
        }
        catch (const mqtt::exception &exc)
        {
            std::cerr << "Resubscription to " << subscription.topic << " failed: " << exc.what() << std::endl;
        }
    }
}

bool MqttClient::publish_message(const std::string &topic, const json &payload,
                                 int pubqos, bool retained)
{
    if (!is_connected())
    {
        std::cerr << "Cannot publish, not connected" << std::endl;
        return false;
    }

    try
    {
        std::string payload_str = payload.dump();
        auto msg = mqtt::make_message(topic, payload_str);
        msg->set_qos(pubqos);
        msg->set_retained(retained);

        publish(msg)->wait();
        return true;
    }
    catch (const mqtt::exception &exc)
    {
        std::cerr << "Publication failed: " << exc.what() << std::endl;
        return false;
    }
}

void MqttClient::on_connect()
{
    std::cout << "Connected to broker: " << server_uri_ << std::endl;

    // Resubscribe to all topics
    resubscribe_all_topics();
}

void MqttClient::on_disconnect()
{
    std::cout << "Disconnected from broker" << std::endl;
}

void MqttClient::attempt_reconnect()
{
    std::cout << "Attempting to reconnect..." << std::endl;

    for (int i = 0; i < nretry_ || nretry_ == -1; ++i)
    {
        try
        {
            std::this_thread::sleep_for(std::chrono::seconds(2));
            std::cout << "Reconnection attempt " << (i + 1) << std::endl;

            connect(conn_opts_)->wait();
            std::cout << "Reconnection successful" << std::endl;
            return;
        }
        catch (const mqtt::exception &e)
        {
            std::cerr << "Reconnection attempt failed: " << e.what() << std::endl;
        }
    }

    std::cerr << "All reconnection attempts failed" << std::endl;
}

void MqttClient::subscription_listener::on_failure(const mqtt::token &tok)
{
    std::cerr << "Subscription failed for topic: " << topic_ << std::endl;
    // Potentially retry subscription or notify of failure
}

void MqttClient::subscription_listener::on_success(const mqtt::token &tok)
{
    std::cout << "Successfully subscribed to topic: " << topic_ << std::endl;
    // Note subscription was successful
}
