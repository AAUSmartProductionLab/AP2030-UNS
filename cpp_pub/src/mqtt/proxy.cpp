#include "mqtt/proxy.h"
#include <iostream>
#include <chrono>

Proxy::Proxy(std::string &address, std::string &client_id,
             mqtt::connect_options &connOpts, int &nretry)
    : mqtt::async_client(address, client_id),
      address(address), connOpts_(connOpts), nretry_(nretry)
{
    router_ = std::make_shared<RouterCallback>();
    set_callback(*router_);
    set_connected_handler([this](const std::string &)
                          { on_connect(); });
    set_disconnected_handler([this](const mqtt::properties &, mqtt::ReasonCode)
                             { on_disconnect(); });
    set_connection_lost_handler([this](const std::string &cause)
                                { on_connection_lost(cause); });
    connect(connOpts_)->wait();
}

void Proxy::register_topic_handler(const std::string &topic,
                                   std::function<void(const json &, mqtt::properties)> callback,
                                   json_validator *validator,
                                   json *schema)
{
    router_->add_handler(topic, callback, validator, schema);
}
void Proxy::on_connect()
{
    std::cout << "Connected to broker " << address << std::endl;
}

void Proxy::on_disconnect()
{
    std::cout << "Disconnected from broker" << std::endl;
}

void Proxy::on_connection_lost(const std::string &cause)
{
    std::cout << "\nConnection lost" << std::endl;
    if (!cause.empty())
        std::cout << "\tcause: " << cause << std::endl;

    std::cout << "Reconnecting..." << std::endl;
    nretry_ = 0;
    attempt_reconnect();
}

void Proxy::attempt_reconnect()
{
    std::cout << "reconnecting" << std::endl;
    std::this_thread::sleep_for(std::chrono::milliseconds(2500));
    try
    {
        connect(connOpts_);
    }
    catch (const mqtt::exception &exc)
    {
        std::cerr << "Error: " << exc.what() << std::endl;
        exit(1);
    }
}