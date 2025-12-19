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
    if (!shared_queue->empty())
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

        // Look up product from blackboard
        auto product_opt = config().blackboard->getAnyLocked("product");
        if (!product_opt)
        {
            std::cerr << "No equipment mapping found for: product" << std::endl;
            return;
        }
        std::string asset_id = product_opt->cast<std::string>();

        // Create Topic objects
        auto response_opt = aas_client_.fetchInterface(asset_id, "config", "output");

        if (!response_opt.has_value())
        {
            std::cerr << "Failed to fetch interface from AAS for node: " << this->name() << std::endl;
            return;
        }

        MqttSubBase::setTopic("output", response_opt.value());
    }
    catch (const std::exception &e)
    {
        std::cerr << "Exception initializing topics from AAS: " << e.what() << std::endl;
    }
}
