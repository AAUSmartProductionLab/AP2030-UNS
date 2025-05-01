#include "bt/CustomNodes/build_production_queue_node.h"
#include "mqtt/utils.h"
#include "mqtt/node_message_distributor.h"
#include <deque>

BuildProductionQueueNode::BuildProductionQueueNode(const std::string &name, const BT::NodeConfig &config, MqttClient &bt_mqtt_client, const mqtt_utils::Topic &response_topic)
    : MqttAsyncSubNode(name, config, bt_mqtt_client,
                       response_topic)
{

    if (MqttSubBase::node_message_distributor_)
    {
        MqttSubBase::node_message_distributor_->registerDerivedInstance(this);
    }
}

BT::PortsList BuildProductionQueueNode::providedPorts()
{
    return {
        BT::details::PortWithDefault<BT::SharedQueue<std::string>>(BT::PortDirection::OUTPUT,
                                                                   "ProductIDs",
                                                                   "{ProductIDs}",
                                                                   "List of product IDs to produce"),

        BT::details::PortWithDefault<std::map<std::string, int>>(BT::PortDirection::OUTPUT,
                                                                 "StationMap",
                                                                 "{StationMap}",
                                                                 "The StationMap of the system for this batch")};
}

void BuildProductionQueueNode::callback(const json &msg, mqtt::properties props)
{
    // Use mutex to protect shared state
    {
        std::lock_guard<std::mutex> lock(mutex_);
        // Update state based on message content
        std::cout << "Received message in BuildProductionQueueNode: " << msg.dump() << std::endl;
        if (status() == BT::NodeStatus::RUNNING)
        {

            // Process the message and update the queue
            int batchSize = msg["BatchSize"];
            auto shared_queue = std::make_shared<std::deque<std::string>>();
            std::cout << "Received message: " << batchSize << std::endl;
            if (batchSize > 0)
            {
                for (int i = 0; i < batchSize; ++i)
                {
                    std::string id = mqtt_utils::generate_uuid();
                    std::cout << "Generated product ID: " << id << std::endl;
                    shared_queue->push_back(id);
                }
                setOutput("ProductIDs", shared_queue);
                setStatus(BT::NodeStatus::SUCCESS);
            }
            else
            {
                setStatus(BT::NodeStatus::FAILURE);
            }
            emitWakeUpSignal();
        }
    }
}