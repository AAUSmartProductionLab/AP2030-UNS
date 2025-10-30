#include "bt/actions/configuration_node.h"
#include "utils.h"
#include "mqtt/node_message_distributor.h"

BT::PortsList ConfigurationNode::providedPorts()
{
    return {
        BT::details::PortWithDefault<BT::SharedQueue<std::string>>(BT::PortDirection::OUTPUT,
                                                                   "ProductIDs",
                                                                   "{ProductIDs}",
                                                                   "List of product IDs to produce")};
}

BT::NodeStatus ConfigurationNode::onStart()
{
    if (!shared_queue->empty() && !stationMap.empty())
    {
        config().blackboard->set("ProductIDs", shared_queue);

        return BT::NodeStatus::SUCCESS;
    }
    return BT::NodeStatus::RUNNING;
}

void ConfigurationNode::callback(const std::string &topic_key, const json &msg, mqtt::properties props)
{
    // Use mutex to protect shared state
    {
        std::lock_guard<std::mutex> lock(mutex_);

        if (msg.contains("Units"))
        {
            // Process the message and update
            int batchSize = msg["Units"];
            if (batchSize > 0)
            {
                for (int i = 0; i < batchSize; ++i)
                {
                    std::string id = mqtt_utils::generate_uuid();
                    shared_queue->push_back(id);
                }
            }
        }
        if (status() == BT::NodeStatus::RUNNING && !shared_queue->empty())
        {
            config().blackboard->set("ProductIDs", shared_queue);

            setStatus(BT::NodeStatus::SUCCESS);
        }
        emitWakeUpSignal();
    }
}

void ConfigurationNode::initializeTopicsFromAAS()
{
    try
    {
        std::string asset_id = station_config_.at(getInput<std::string>("Asset").value());
        // Create Topic objects
        mqtt_utils::Topic response = aas_client_.fetchInterface(asset_id, getInput<std::string>("Command").value(), "response").value();
        MqttSubBase::setTopic("response", response);
    }
    catch (const std::exception &e)
    {
        std::cerr << "Exception initializing topics from AAS: " << e.what() << std::endl;
    }
}
