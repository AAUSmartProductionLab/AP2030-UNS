#include "bt/decorators/get_product_from_queue_node.h"
#include <behaviortree_cpp/bt_factory.h>
#include <nlohmann/json.hpp>
#include <string>
#include "aas/aas_client.h"
#include "mqtt/mqtt_pub_base.h"

void GetProductFromQueue::initializeTopicsFromAAS()
{
    try
    {
        std::string asset_id = aas_client_.getInstanceNameByAssetName(this->config().blackboard->get<std::string>("XbotTopic"));
        // Create Topic objects
        mqtt_utils::Topic request_topic = aas_client_.fetchInterface(asset_id, this->name(), "ProductID").value();

        MqttPubBase::setTopic("ProductID", request_topic);
    }
    catch (const std::exception &e)
    {
        std::cerr << "Exception initializing topics from AAS: " << e.what() << std::endl;
    }
}

BT::NodeStatus GetProductFromQueue::tick()
{
    bool popped = false;
    if (status() == BT::NodeStatus::IDLE)
    {
        child_running_ = false;

        // Always get a fresh queue reference when starting from IDLE
        BT::AnyPtrLocked any_ref = getLockedPortContent("Queue");
        if (any_ref)
        {
            queue_ = any_ref.get()->cast<BT::SharedQueue<std::string>>();
        }
    }

    if (!child_running_)
    {
        if (queue_ && !queue_->empty())
        {
            auto value = std::move(queue_->front());
            queue_->pop_front();
            popped = true;

            // Publish the product ID to the MQTT topic
            json message;
            message["ProductId"] = value;
            message["TimeStamp"] = bt_utils::getCurrentTimestampISO();
            MqttPubBase::publish("ProductID", message); // Use the "ProductID" key

            setOutput("ProductID", value);
        }
    }

    if (!popped && !child_running_)
    {
        return getInput<BT::NodeStatus>("if_empty").value();
    }

    if (status() == BT::NodeStatus::IDLE)
    {
        setStatus(BT::NodeStatus::RUNNING);
    }

    BT::NodeStatus child_state = child_node_->executeTick();
    child_running_ = (child_state == BT::NodeStatus::RUNNING);

    if (isStatusCompleted(child_state))
    {
        resetChild();
    }

    if (child_state == BT::NodeStatus::FAILURE)
    {
        return BT::NodeStatus::FAILURE;
    }
    return BT::NodeStatus::RUNNING;
}

BT::PortsList GetProductFromQueue::providedPorts()
{
    // we mark "Queue" as BidirectionalPort, because the original element is modified
    return {
        BT::details::PortWithDefault<BT::SharedQueue<std::string>>(
            BT::PortDirection::INPUT,
            "Queue",
            "{ProductIDs}",
            "The queue of all product IDs of the batch"),
        BT::InputPort<BT::NodeStatus>("if_empty", BT::NodeStatus::SUCCESS,
                                      "Status to return if queue is empty: "
                                      "SUCCESS, FAILURE, SKIPPED"),
        BT::details::PortWithDefault<std::string>(
            BT::PortDirection::OUTPUT,
            "ProductID",
            "{ProductID}",
            "The product ID of the current product")};
}