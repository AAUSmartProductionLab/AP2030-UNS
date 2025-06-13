#pragma once

#include "bt/mqtt_action_node.h"
#include <behaviortree_cpp/bt_factory.h>
#include <nlohmann/json.hpp>
#include "utils.h"
#include <string>

// Forward declarations
class MqttClient;
using nlohmann::json;

class RefillNode : public MqttActionNode
{
private:
    double weight_ = 0.0;

public:
    RefillNode(const std::string &name,
               const BT::NodeConfig &config,
               MqttClient &mqtt_client,
               const mqtt_utils::Topic &request_topic,
               const mqtt_utils::Topic &response_topic,
               const mqtt_utils::Topic &weight_topic)
        : MqttActionNode(name, config, mqtt_client,
                         request_topic,
                         response_topic)
    {
        MqttSubBase::topics_["weight"] = weight_topic; // add the weight topic to the subscriber
        for (auto &[key, topic_obj] : MqttPubBase::topics_)
        {
            topic_obj.setTopic(getFormattedTopic(topic_obj.getPattern()));
        }
        for (auto &[key, topic_obj] : MqttSubBase::topics_)
        {
            topic_obj.setTopic(getFormattedTopic(topic_obj.getPattern()));
        }
        if (MqttSubBase::node_message_distributor_)
        {
            MqttSubBase::node_message_distributor_->registerDerivedInstance(this);
        }
    }
    ~RefillNode()
    {
        if (MqttSubBase::node_message_distributor_)
        {
            MqttSubBase::node_message_distributor_->unregisterInstance(this);
        }
    }
    static BT::PortsList providedPorts()
    {
        return {BT::details::PortWithDefault<std::string>(
                    BT::PortDirection::INPUT,
                    "Station",
                    "{Station}",
                    "The station to register with"),
                BT::details::PortWithDefault<std::string>(
                    BT::PortDirection::INPUT,
                    "Command",
                    "Refill",
                    "The command to execute on the station"),
                BT::details::PortWithDefault<std::string>(
                    BT::PortDirection::INPUT,
                    "Uuid",
                    "{ID}",
                    "UUID for the command to execute")};
    }
    json createMessage() override
    {
        json message;
        BT::Expected<std::string> uuid_result = getInput<std::string>("Uuid");
        if (uuid_result)
        {
            current_uuid_ = uuid_result.value();
        }
        else
        {
            std::cerr << "Error: Uuid not provided to StationExecuteNode. Error: "
                      << uuid_result.error() << std::endl;

            current_uuid_ = mqtt_utils::generate_uuid();
            std::cerr << "Using generated UUID instead: " << current_uuid_ << std::endl;
        }
        message["Uuid"] = current_uuid_;
        message["StartWeight"] = weight_;

        return message;
    }
    std::string getFormattedTopic(const std::string &pattern)
    {
        std::vector<std::string> replacements;
        BT::Expected<std::string> station = getInput<std::string>("Station");
        BT::Expected<std::string> command = getInput<std::string>("Command");
        if (station.has_value() && command.has_value())
        {
            replacements.push_back(station.value());
            replacements.push_back(command.value());
            return mqtt_utils::formatWildcardTopic(pattern, replacements);
        }
        return pattern;
    }
    // Standard implementation based on PackML override this if needed
    void callback(const std::string &topic_key, const json &msg, mqtt::properties props) override
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
    template <typename DerivedNode>
    static void registerNodeType(
        BT::BehaviorTreeFactory &factory,
        NodeMessageDistributor &distributor,
        MqttClient &mqtt_client,
        const std::string &node_name,
        const mqtt_utils::Topic &request_topic,
        const mqtt_utils::Topic &response_topic,
        const mqtt_utils::Topic &weight_topic)
    {
        MqttSubBase::setNodeMessageDistributor(&distributor);
        factory.registerBuilder<DerivedNode>(
            node_name,
            [mqtt_client_ptr = &mqtt_client, request_topic, response_topic, weight_topic](const std::string &name, const BT::NodeConfig &config)
            {
                return std::make_unique<DerivedNode>(
                    name, config, *mqtt_client_ptr,
                    request_topic, response_topic, weight_topic);
            });
    }
};