#include "backends/mqtt/imqtt_subscriber.h"
#include "utils.h"
#include <mqtt/async_client.h>
#include <iostream>

void IMqttSubscriber::processMessage(const std::string &actual_topic_str,
                                     const nlohmann::json &msg,
                                     mqtt::properties props)
{
    for (auto const &[key, topic_obj] : topics_)
    {
        if (mqtt_utils::topicMatches(topic_obj.getTopic(), actual_topic_str))
        {
            if (topic_obj.validateMessage(msg))
            {
                callback(key, msg, props);
                return;
            }
            else
            {
                std::cerr << getBTNodeName()
                          << ": Message validation failed for topic key '"
                          << key << "' on actual topic '"
                          << actual_topic_str << "'" << std::endl;
                return;
            }
        }
    }
}

void IMqttSubscriber::setTopic(const std::string &topic_key,
                               const mqtt_utils::Topic &topic_object)
{
    topics_[topic_key] = topic_object;
}
