#include "mqtt/callbacks.h"
#include <iostream>

void RouterCallback::message_arrived(mqtt::const_message_ptr msg)
{
    std::string topic = msg->get_topic();

    try
    {
        json payload = json::parse(msg->get_payload());
        mqtt::properties props = msg->get_properties();

        bool handled = false;
        for (const auto &handler : handlers_)
        {
            if (topic == handler.topic || topic.find(handler.topic) != std::string::npos)
            {
                handler.callback(payload, props);
                handled = true;
            }
        }

        if (!handled)
        {
            std::cout << "No handler found for topic: " << topic << std::endl;
        }
    }
    catch (const std::exception &e)
    {
        std::cerr << "Error processing message: " << e.what() << std::endl;
    }
}

void RouterCallback::add_handler(const std::string &topic,
                                 std::function<void(const json &, mqtt::properties)> callback,
                                 json_validator *validator,
                                 json *schema)
{
    handlers_.push_back({topic, callback, validator, schema});
    std::cout << "Added handler for topic: " << topic << std::endl;
}

TopicCallback::TopicCallback(std::function<void(const json &, mqtt::properties)> callback_method,
                             json_validator &validator,
                             json &sub_schema,
                             std::string &subtopic)
    : callback_method_(callback_method),
      sub_validator_(validator),
      sub_schema_(sub_schema),
      subtopic_(subtopic)
{
}

void TopicCallback::message_arrived(mqtt::const_message_ptr msg)
{
    // Only process messages for our specific subtopic
    if (msg->get_topic() != subtopic_)
    {
        std::cout << "Ignoring message for different topic" << std::endl;
        return;
    }

    json received_msg = json::parse(msg->get_payload());

    if (!sub_schema_.is_null())
    {
        sub_validator_.validate(received_msg);
    }

    if (callback_method_)
    {
        mqtt::properties props = msg->get_properties();
        callback_method_(received_msg, props);
    }
}