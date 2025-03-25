#include "mqtt/mqtttopic.h"
#include "mqtt/proxy.h"
#include "mqtt/utils.h"
#include <iostream>
#include <mqtt/message.h>
#include <mqtt/exception.h>

// MqttTopic implementation
MqttTopic::MqttTopic(const std::string &topic, const std::string &publish_schema_path,
                     const std::string &subscribe_schema_path, int qos,
                     std::function<void(const json &, mqtt::properties)> callback_method)
    : qos(qos), callback_method(callback_method)
{
    pub_schema = mqtt_utils::load_schema(publish_schema_path);
    sub_schema = mqtt_utils::load_schema(subscribe_schema_path);

    if (!pub_schema.is_null())
    {
        try
        {
            pub_validator.set_root_schema(pub_schema);
        }
        catch (const std::exception &e)
        {
            std::cerr << "Validation of schema failed, here is why: " << e.what() << "\n";
        }
        pubtopic = topic + "/CMD" + pub_schema.value("subtopic", "");
    }
    else
    {
        pubtopic = topic;
    }

    if (!sub_schema.is_null())
    {
        sub_validator.set_root_schema(sub_schema);
        subtopic = topic + "/DATA" + sub_schema.value("subtopic", "");
    }
    else
    {
        subtopic = topic;
    }
}

void MqttTopic::publish(mqtt::async_client &client, const json &message)
{
    try
    {
        if (!pub_schema.is_null())
        {
            pub_validator.validate(message);
        }

        std::string correlation_data = mqtt_utils::generate_uuid();
        mqtt::property correlation_property(mqtt::property::code::CORRELATION_DATA, correlation_data);
        mqtt::property response_topic(mqtt::property::code::RESPONSE_TOPIC, subtopic);
        mqtt::properties props;
        props.add(correlation_property);
        props.add(response_topic);

        if (!pubtopic.empty())
        {
            mqtt::message_ptr pubmsg = mqtt::make_message(pubtopic, message.dump(), qos, false, props);
            try
            {
                client.publish(pubmsg)->wait_for(std::chrono::seconds(10));
            }
            catch (const mqtt::exception &exc)
            {
                std::cerr << exc.what() << std::endl;
                client.reconnect();
            }
        }
    }
    catch (std::exception &e)
    {
        std::cout << "Exception when setting up validating: " << e.what() << std::endl;
        return;
    }
}

void MqttTopic::subscribe(mqtt::async_client &client)
{
    if (!subtopic.empty())
    {
        client.subscribe(subtopic, qos);
    }
}

void MqttTopic::register_callback(Proxy &proxy)
{
    if (!subtopic.empty())
    {
        proxy.register_topic_handler(subtopic, callback_method, &sub_validator, &sub_schema);
        std::cout << "Registered callback for topic: " << subtopic << std::endl;
    }
}

// Response implementation
Response::Response(std::string topic, std::string publish_schema_path,
                   std::string subscribe_schema_path, int qos,
                   std::function<void(const json &, mqtt::properties)> callback_method)
    : MqttTopic(topic, publish_schema_path, subscribe_schema_path, qos, callback_method)
{
}

void Response::publish(mqtt::async_client &client, const json &request, mqtt::properties &props)
{
    if (!pub_schema.is_null())
    {
        pub_validator.validate(request);
    }

    props.add(mqtt::property(mqtt::property::code::CORRELATION_DATA, mqtt_utils::generate_uuid()));

    try
    {
        std::string response_topic = mqtt::get<std::string>(props.get(mqtt::property::code::RESPONSE_TOPIC));
        client.publish(response_topic, request.dump(), qos, false, props);
    }
    catch (const std::exception &e)
    {
        // Handle the case where RESPONSE_TOPIC is not present
        std::cout << "Error: User Property RESPONSE_TOPIC not found, " << e.what() << std::endl;
    }
}

// Request implementation
Request::Request(std::string topic, std::string publish_schema_path,
                 std::string subscribe_schema_path, int qos,
                 std::function<void(const json &, mqtt::properties)> callback_method)
    : MqttTopic(topic, publish_schema_path, subscribe_schema_path, qos, callback_method)
{
    subtopic = pubtopic + sub_schema["subtopic"].get<std::string>() + "/" + mqtt_utils::generate_uuid();
}