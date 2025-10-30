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
        std::string asset_id = aas_client_.getInstanceNameByAssetName(this->config().blackboard->get<std::string>("XbotTopic"));
        // Create Topic objects
        mqtt_utils::Topic product_association = aas_client_.fetchInterface(asset_id, this->name(), "product_association").value();
        MqttPubBase::setTopic("request", product_association);
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