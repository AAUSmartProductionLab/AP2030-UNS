#pragma once
#include <mqtt/async_client.h>
#include <nlohmann/json.hpp>
#include <nlohmann/json-schema.hpp>
#include "callbacks.h"

using nlohmann::json;
using nlohmann::json_schema::json_validator;

class Proxy : public mqtt::async_client
{
private:
    std::string &address;
    mqtt::connect_options &connOpts_;
    int &nretry_;
    std::shared_ptr<RouterCallback> router_;

    void on_connect();
    void on_disconnect();
    void on_connection_lost(const std::string &cause);
    void attempt_reconnect();

public:
    Proxy(std::string &address, std::string &client_id,
          mqtt::connect_options &connOpts, int &nretry);

    void register_topic_handler(const std::string &topic,
                                std::function<void(const json &, mqtt::properties)> callback,
                                json_validator *validator = nullptr,
                                json *schema = nullptr);
};