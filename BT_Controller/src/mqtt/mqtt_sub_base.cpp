#include "mqtt/mqtt_sub_base.h"
#include "mqtt/node_message_distributor.h"
#include "utils.h"
#include <iostream>
#include "behaviortree_cpp/blackboard.h"

namespace fs = std::filesystem;
// Initialize the static member
NodeMessageDistributor *MqttSubBase::node_message_distributor_ = nullptr;

MqttSubBase::MqttSubBase(MqttClient &mqtt_client)
    : mqtt_client_(mqtt_client)
{
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

void MqttSubBase::setTopic(const std::string &topic_key, const mqtt_utils::Topic &topic_object)
{
    topics_[topic_key] = topic_object;
}
