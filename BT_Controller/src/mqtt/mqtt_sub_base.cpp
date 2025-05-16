#include "mqtt/mqtt_sub_base.h"
#include "mqtt/node_message_distributor.h"
#include "utils.h"
#include <iostream>

namespace fs = std::filesystem;
// Initialize the static member
NodeMessageDistributor *MqttSubBase::node_message_distributor_ = nullptr;

MqttSubBase::MqttSubBase(MqttClient &mqtt_client,
                         const std::map<std::string, mqtt_utils::Topic> &topics)
    : mqtt_client_(mqtt_client),
      topics_(topics)
{
    for (auto &pair : topics_)
    {
        pair.second.initValidator(); // Initialize validator for each topic
    }
}

void MqttSubBase::processMessage(const std::string &actual_topic_str, const json &msg, mqtt::properties props)
{
    for (auto const &[key, topic_obj] : topics_)
    {
        // Check if the incoming actual_topic_str matches the pattern of topic_obj.getTopic()
        // topic_obj.getTopic() should be the (potentially wildcarded) string subscribed to.
        if (mqtt_utils::topicMatches(topic_obj.getTopic(), actual_topic_str))
        {
            if (topic_obj.validateMessage(msg))
            {
                callback(key, msg, props); // Pass the logical key
                return;                    // Assuming one message is handled by one callback logic path per instance
            }
            else
            {
                std::cerr << getBTNodeName() << ": Message validation failed for topic key '" << key
                          << "' on actual topic '" << actual_topic_str << "'" << std::endl;
                return;
            }
        }
    }
    // Optional: Log if no topic in this sub-base instance matched.
}

void MqttSubBase::setNodeMessageDistributor(NodeMessageDistributor *manager)
{
    node_message_distributor_ = manager;
}