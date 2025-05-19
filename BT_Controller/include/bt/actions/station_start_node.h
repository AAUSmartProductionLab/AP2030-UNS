#pragma once

#include "bt/mqtt_action_node.h"
#include <behaviortree_cpp/bt_factory.h>
#include <nlohmann/json.hpp>
#include "utils.h"
#include <string>

// Forward declarations
class MqttClient;
using nlohmann::json;

class StationStartNode : public MqttActionNode
{
public:
    StationStartNode(const std::string &name,
                     const BT::NodeConfig &config,
                     MqttClient &mqtt_client,
                     const mqtt_utils::Topic &request_topic,
                     const mqtt_utils::Topic &response_topic,
                     const mqtt_utils::Topic &halt_topic)
        : MqttActionNode(name, config, mqtt_client,
                         request_topic,
                         response_topic,
                         halt_topic)
    {
        for (auto &[key, topic_obj] : MqttPubBase::topics_)
        {
            topic_obj.setTopic(getFormattedTopic(topic_obj.getPattern()));
        }
        // For SubBase topics
        for (auto &[key, topic_obj] : MqttSubBase::topics_)
        {
            topic_obj.setTopic(getFormattedTopic(topic_obj.getPattern()));
        }

        if (MqttSubBase::node_message_distributor_)
        {
            MqttSubBase::node_message_distributor_->registerDerivedInstance(this);
        }
    }
    ~StationStartNode()
    {
        if (MqttSubBase::node_message_distributor_)
        {
            MqttSubBase::node_message_distributor_->unregisterInstance(this);
        }
    }
    static BT::PortsList providedPorts()
    {
        return {
            BT::details::PortWithDefault<std::string>(
                BT::PortDirection::INPUT,
                "Station",
                "{Station}",
                "The station to register with"),
            BT::details::PortWithDefault<std::string>(
                BT::PortDirection::INPUT,
                "Uuid",
                "{ID}",
                "UUID for the command to execute")};
    }
    json createMessage() override
    {
        json message;
        BT::Expected<std::string> uuid = getInput<std::string>("Uuid");
        if (uuid.has_value())
        {
            current_uuid_ = uuid.value();
            message["Uuid"] = current_uuid_;
            return message;
        }
        return json();
    }

    std::string getFormattedTopic(const std::string &pattern)
    {
        BT::Expected<std::string> station = getInput<std::string>("Station");
        if (station.has_value())
        {
            return mqtt_utils::formatWildcardTopic(pattern, station.value());
        }
        return pattern;
    }

    void onHalted() override
    {
        json message;
        message["Uuid"] = current_uuid_;
        MqttPubBase::publish("halt", message);
    }
    void callback(const std::string &topic_key, const json &msg, mqtt::properties props) override
    {
        {
            std::lock_guard<std::mutex> lock(mutex_);
            if (status() == BT::NodeStatus::RUNNING &&
                !msg["ProcessQueue"].empty() &&
                msg["ProcessQueue"][0] == current_uuid_)
            {
                if (msg["State"] == "STOPPING")
                {
                    current_uuid_ = "";
                    setStatus(BT::NodeStatus::FAILURE);
                }
                else if (msg["State"] == "EXECUTE")
                {
                    current_uuid_ = "";
                    setStatus(BT::NodeStatus::SUCCESS);
                }
                emitWakeUpSignal();
            }
        }
    }
};