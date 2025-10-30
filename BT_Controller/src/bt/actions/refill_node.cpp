#include "bt/mqtt_action_node.h"
#include <behaviortree_cpp/bt_factory.h>
#include <nlohmann/json.hpp>
#include "utils.h"
#include <string>
#include "bt/actions/refill_node.h"

void RefillNode::initializeTopicsFromAAS()
{
    try
    {
        std::string asset_id = station_config_.at(getInput<std::string>("Asset").value()); // Check action:asset association in json message
        // Create Topic objects
        mqtt_utils::Topic request_topic = aas_client_.fetchInterface(asset_id, this->name(), "request").value();
        mqtt_utils::Topic response_topic = aas_client_.fetchInterface(asset_id, this->name(), "response").value();
        mqtt_utils::Topic weight_topic = aas_client_.fetchInterface(asset_id, this->name(), "weight").value();

        MqttPubBase::setTopic("request", request_topic);
        MqttSubBase::setTopic("response", response_topic);
        MqttSubBase::setTopic("weight", weight_topic);
    }
    catch (const std::exception &e)
    {
        std::cerr << "Exception initializing topics from AAS: " << e.what() << std::endl;
    }
}

BT::PortsList RefillNode::providedPorts()
{
    return {BT::details::PortWithDefault<std::string>(
                BT::PortDirection::INPUT,
                "Asset",
                "{Asset}",
                "The asset used for refilling"),
            BT::details::PortWithDefault<std::string>(
                BT::PortDirection::INPUT,
                "Uuid",
                "{ID}",
                "UUID for the command to execute")};
}

json RefillNode::createMessage()
{
    json message;
    BT::Expected<std::string> uuid = getInput<std::string>("Uuid");
    if (uuid)
    {
        current_uuid_ = uuid.value();
    }
    else
    {
        std::cerr << "Error: Uuid not provided to StationExecuteNode. Error: "
                  << uuid.error() << std::endl;

        current_uuid_ = mqtt_utils::generate_uuid();
        std::cerr << "Using generated UUID instead: " << current_uuid_ << std::endl;
    }
    message["Uuid"] = current_uuid_;
    message["StartWeight"] = weight_;

    return message;
}

// Standard implementation based on PackML override this if needed
void RefillNode::callback(const std::string &topic_key, const json &msg, mqtt::properties props)
{
    // Use mutex to protect shared state
    {
        std::lock_guard<std::mutex> lock(mutex_);
        BT::Expected<std::string> uuid = getInput<std::string>("Uuid");

        if (topic_key == "weight" && uuid.has_value()) // allways update weight so we have the latest for the product when we make the command message
        {
            current_uuid_ = uuid.value();
            if (msg.contains("Uuid") && msg["Uuid"] == current_uuid_ && msg.contains("Weight"))
            {
                weight_ = msg["Weight"];
            }
        }
        else if (topic_key == "response")
        {
            if (status() == BT::NodeStatus::RUNNING)
            {
                if (msg["Uuid"] == current_uuid_)
                {

                    if (msg["State"] == "FAILURE")
                    {
                        current_uuid_ = "";
                        setStatus(BT::NodeStatus::FAILURE);
                    }
                    else if (msg["State"] == "SUCCESS")
                    {
                        current_uuid_ = "";
                        setStatus(BT::NodeStatus::SUCCESS);
                    }
                    else if (msg["State"] == "RUNNING")
                    {
                        setStatus(BT::NodeStatus::RUNNING);
                    }
                }
                emitWakeUpSignal();
            }
        }
    }
}
