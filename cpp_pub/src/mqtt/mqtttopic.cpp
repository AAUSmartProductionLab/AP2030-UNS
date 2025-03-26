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
        if (!pubtopic.empty())
        {
            mqtt::message_ptr pubmsg = mqtt::make_message(pubtopic, message.dump(), qos, false);
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
        std::cout << "Exception when validating: " << e.what() << std::endl;
        return;
    }
}

void MqttTopic::register_callback(Proxy &proxy)
{
    if (!subtopic.empty())
    {
        // Update to use the new simplified interface
        auto wrapped_callback = [this](const json &message, mqtt::properties props)
        {
            try
            {
                // Validate the message if we have a schema
                if (!sub_schema.is_null())
                {
                    sub_validator.validate(message);
                }
                // Call the original callback
                callback_method(message, props);
            }
            catch (const std::exception &e)
            {
                std::cerr << "Validation error: " << e.what() << std::endl;
            }
        };

        proxy.register_topic_handler(subtopic, wrapped_callback);
        std::cout << "Registered callback for topic: " << subtopic << std::endl;
    }
}