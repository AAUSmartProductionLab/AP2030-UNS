#pragma once
#include <functional>
#include <string>
#include <mqtt/async_client.h>
#include <nlohmann/json.hpp>
#include <nlohmann/json-schema.hpp>

// Forward declarations
class Proxy;

using nlohmann::json;
using nlohmann::json_schema::json_validator;

class MqttTopic
{
private:
    std::string pubtopic;
    std::string subtopic;
    int qos;
    json pub_schema;
    json sub_schema;
    json_validator pub_validator;
    json_validator sub_validator;
    std::function<void(const json &, mqtt::properties)> callback_method;

public:
    MqttTopic(const std::string &topic,
              const std::string &publish_schema_path,
              const std::string &subscribe_schema_path,
              int qos,
              std::function<void(const json &, mqtt::properties)> callback_method);

    void publish(mqtt::async_client &client, const json &message);
    void register_callback(Proxy &proxy);
};

class Response : public MqttTopic
{
public:
    Response(std::string topic, std::string publish_schema_path,
             std::string subscribe_schema_path, int qos = 0,
             std::function<void(const json &, mqtt::properties)> callback_method = nullptr);

    void publish(mqtt::async_client &client, const json &request, mqtt::properties &props);
};

class Request : public MqttTopic
{
public:
    Request(std::string topic, std::string publish_schema_path,
            std::string subscribe_schema_path, int qos = 0,
            std::function<void(const json &, mqtt::properties)> callback_method = nullptr);
};