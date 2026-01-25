#include "bt/decorators/get_product_from_queue_node.h"
#include <behaviortree_cpp/bt_factory.h>
#include <nlohmann/json.hpp>
#include <string>
#include "aas/aas_client.h"
#include "mqtt/mqtt_pub_base.h"

void GetProductFromQueue::initializeTopicsFromAAS()
{
    // Already initialized, skip
    if (topics_initialized_)
    {
        return;
    }

    try
    {
        auto xbot_topic_opt = this->config().blackboard->getAnyLocked("XbotTopic");
        if (!xbot_topic_opt)
        {
            std::cerr << "Node '" << this->name() << "' cannot access XbotTopic from blackboard" << std::endl;
            return;
        }

        std::string xbot_topic = xbot_topic_opt->cast<std::string>();
        std::cout << "Node '" << this->name() << "' initializing for XbotTopic: " << xbot_topic << std::endl;

        // Use xbot_topic directly (should be resolved from blackboard)
        std::string asset_id = xbot_topic;

        // Create Topic objects
        auto request_opt = aas_client_.fetchInterface(asset_id, this->name(), "ProductID");

        if (!request_opt.has_value())
        {
            std::cerr << "Failed to fetch interface from AAS for node: " << this->name() << std::endl;
            return;
        }

        MqttPubBase::setTopic("ProductID", request_opt.value());
        topics_initialized_ = true;
    }
    catch (const std::exception &e)
    {
        std::cerr << "Exception initializing topics from AAS: " << e.what() << std::endl;
    }
}

BT::NodeStatus GetProductFromQueue::tick()
{
    // Ensure lazy initialization is done
    if (!ensureInitialized())
    {
        std::cerr << "Node '" << this->name() << "' could not be initialized, returning FAILURE" << std::endl;
        return BT::NodeStatus::FAILURE;
    }

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