#pragma once
#include <vector>
#include <functional>
#include <string>

// Include MQTT headers
#include <mqtt/async_client.h>
#include <mqtt/properties.h>

#include <nlohmann/json.hpp>
#include <nlohmann/json-schema.hpp>

using nlohmann::json;
using nlohmann::json_schema::json_validator;

class TopicCallback : public virtual mqtt::callback
{
private:
    std::function<void(const json &, mqtt::properties)> callback_method_;
    json &sub_schema_;
    json_validator &sub_validator_;
    std::string &subtopic_;

public:
    TopicCallback(std::function<void(const json &, mqtt::properties)> callback_method,
                  json_validator &validator, json &sub_schema, std::string &subtopic);
    void message_arrived(mqtt::const_message_ptr msg) override;
};

class RouterCallback : public mqtt::callback
{
private:
    struct Handler
    {
        std::string topic;
        std::function<void(const json &, mqtt::properties)> callback;
        json_validator *validator;
        json *schema;
    };
    std::vector<Handler> handlers_;

public:
    void message_arrived(mqtt::const_message_ptr msg) override;
    void add_handler(const std::string &topic,
                     std::function<void(const json &, mqtt::properties)> callback,
                     json_validator *validator = nullptr,
                     json *schema = nullptr);
};
