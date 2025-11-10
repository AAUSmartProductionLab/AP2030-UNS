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
        auto asset_input = getInput<std::string>("Asset");
        if (!asset_input.has_value())
        {
            std::cerr << "Node '" << this->name() << "' has no Asset input configured" << std::endl;
            return;
        }

        std::string asset_name = asset_input.value();

        std::string asset_id = aas_client_.getInstanceNameByAssetName(asset_name);

        // Create Topic objects
        auto request_opt = aas_client_.fetchInterface(asset_id, "dispense", "input");
        auto response_opt = aas_client_.fetchInterface(asset_id, "dispense", "output");
        auto weight_opt = aas_client_.fetchInterface(asset_id, "weight", "output");

        if (!request_opt.has_value() || !response_opt.has_value() || !weight_opt.has_value())
        {

            std::cout << "Node '" << this->name() << "' initializing for Asset: " << asset_name << std::endl;
            std::cout << "Initializing MQTT topics for asset ID: " << asset_id << std::endl;
            std::cerr << "Failed to fetch interfaces from AAS for node: " << this->name() << std::endl;
            return;
        }

        MqttPubBase::setTopic("input", request_opt.value());
        MqttSubBase::setTopic("output", response_opt.value());
        MqttSubBase::setTopic("weight", weight_opt.value());
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

nlohmann::json RefillNode::createMessage()
{
    nlohmann::json message;
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
void RefillNode::callback(const std::string &topic_key, const nlohmann::json &msg, mqtt::properties props)
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
        else if (topic_key == "output")
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
