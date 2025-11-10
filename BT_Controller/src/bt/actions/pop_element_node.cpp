#include <behaviortree_cpp/bt_factory.h>
#include <string>
#include "mqtt/mqtt_pub_base.h"
#include <nlohmann/json.hpp>
#include "bt/actions/pop_element_node.h"
#include "aas/aas_client.h"

void PopElementNode::initializeTopicsFromAAS()
{
    try
    {
        auto xbot_topic_opt = this->config().blackboard->getAnyLocked("Xbot");
        if (!xbot_topic_opt)
        {
            std::cerr << "Node '" << this->name() << "' cannot access XbotTopic from blackboard" << std::endl;
            return;
        }

        std::string xbot_topic = xbot_topic_opt->cast<std::string>();
        std::cout << "Node '" << this->name() << "' initializing for XbotTopic: " << xbot_topic << std::endl;

        std::string asset_id = aas_client_.getInstanceNameByAssetName(xbot_topic);
        std::cout << "Initializing MQTT topics for asset ID: " << asset_id << std::endl;

        // Create Topic objects
        auto product_association_opt = aas_client_.fetchInterface(asset_id, this->name(), "product_association");

        if (!product_association_opt.has_value())
        {
            std::cerr << "Failed to fetch interface from AAS for node: " << this->name() << std::endl;
            return;
        }

        MqttPubBase::setTopic("input", product_association_opt.value());
    }
    catch (const std::exception &e)
    {
        std::cerr << "Exception initializing topics from AAS: " << e.what() << std::endl;
    }
}

nlohmann::json PopElementNode::createMessage()
{
    std::string product_id_to_publish;
    BT::NodeStatus status_if_queue_empty_or_invalid = getInput<BT::NodeStatus>("if_empty").value_or(BT::NodeStatus::FAILURE);
    {
        BT::AnyPtrLocked any_ref = getLockedPortContent("Queue");

        if (!any_ref)
        {
            return status_if_queue_empty_or_invalid;
        }

        BT::Expected<BT::SharedQueue<std::string>> queue_expected = any_ref.get()->cast<BT::SharedQueue<std::string>>();
        if (!queue_expected)
        {
            return status_if_queue_empty_or_invalid;
        }

        BT::SharedQueue<std::string> queue_ptr = queue_expected.value();
        if (!queue_ptr)
        {
            return status_if_queue_empty_or_invalid;
        }

        if (queue_ptr->empty())
        {
            return status_if_queue_empty_or_invalid;
        }

        product_id_to_publish = std::move(queue_ptr->front());
        queue_ptr->pop_front();
    }

    json message;
    message["ProductId"] = product_id_to_publish;
    message["TimeStamp"] = bt_utils::getCurrentTimestampISO();
    return message;
}

BT::PortsList PopElementNode::providedPorts()
{
    return {
        BT::InputPort<BT::SharedQueue<std::string>>(
            "Queue",
            "{ProductIDs}",
            "The shared queue of product IDs. An element will be popped from it."),
        BT::InputPort<BT::NodeStatus>("if_empty", BT::NodeStatus::SUCCESS,
                                      "Status to return if the queue is empty or invalid (SUCCESS, FAILURE, SKIPPED)."),
        BT::OutputPort<std::string>(
            "ProductID",
            "{ProductID}",
            "The product ID popped from the queue.")};
}