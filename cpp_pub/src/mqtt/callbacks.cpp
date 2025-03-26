#include "mqtt/callbacks.h"
#include <iostream>

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