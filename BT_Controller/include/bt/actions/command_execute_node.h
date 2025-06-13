#pragma once

#include "bt/mqtt_action_node.h"
#include <behaviortree_cpp/bt_factory.h>
#include <nlohmann/json.hpp>
#include "utils.h"
#include <string>
#include <cctype> // For std::isspace

// Forward declarations
class MqttClient;
using nlohmann::json;

namespace BT
{
    inline StringView trim_string_view(StringView sv)
    {
        if (sv.empty())
        {
            return sv;
        }
        size_t first = 0;
        while (first < sv.size() && std::isspace(static_cast<unsigned char>(sv[first])))
        {
            ++first;
        }
        if (first == sv.size()) // All whitespace
        {
            return StringView(sv.data() + first, 0);
        }

        size_t last = sv.size() - 1;
        while (last > first && std::isspace(static_cast<unsigned char>(sv[last])))
        {
            --last;
        }
        return sv.substr(first, (last - first) + 1);
    }

    template <>
    inline json convertFromString(StringView str_param)
    {
        StringView s = trim_string_view(str_param);
        if (s.size() >= 2 && s.front() == '\'' && s.back() == '\'')
        {
            StringView inner_content = s.substr(1, s.size() - 2);
            try
            {
                return json::parse(inner_content);
            }
            catch (const json::parse_error &e)
            {
                std::string error_message = "Failed to parse JSON from single-quoted string. Inner content: '";
                error_message.append(inner_content);
                error_message += "'. Details: ";
                error_message += e.what();
                throw RuntimeError(error_message);
            }
        }
        else
            throw RuntimeError(
                "Invalid Parameter format. Expected single-quoted json string like '\"{\\\"key\\\": \\\"value\\\"}\"'");
    }
};

class CommandExecuteNode : public MqttActionNode
{
public:
    CommandExecuteNode(const std::string &name,
                       const BT::NodeConfig &config,
                       MqttClient &mqtt_client,
                       const mqtt_utils::Topic &request_topic,
                       const mqtt_utils::Topic &response_topic)
        : MqttActionNode(name, config, mqtt_client,
                         request_topic,
                         response_topic)
    {
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
    ~CommandExecuteNode()
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
                    "Entity",
                    "{Station}",
                    "The station to register with"),
                BT::details::PortWithDefault<std::string>(
                    BT::PortDirection::INPUT,
                    "Command",
                    "Command",
                    "The command to execute on the station"),
                BT::details::PortWithDefault<std::string>(
                    BT::PortDirection::INPUT,
                    "Uuid",
                    "{Uuid}",
                    "UUID for the command to execute"),
                BT::details::PortWithDefault<json>(
                    BT::PortDirection::INPUT,
                    "Parameters",
                    "'{}'",
                    "The weight to refill, if not provided it will be set to 0.0")};
    }
    json createMessage() override
    {
        json message;
        BT::Expected<std::string> uuid = getInput<std::string>("Uuid");
        if (uuid && uuid.has_value() && !uuid.value().empty())
        {
            current_uuid_ = uuid.value();
        }
        else
        {
            current_uuid_ = mqtt_utils::generate_uuid();
        }
        BT::Expected<json> params = getInput<json>("Parameters");

        if (params)
        {
            if (!params.value().empty() && params.value().is_object())
            {
                message.update(params.value());
            }
        }
        else
        {
            std::cerr << "Warning: Could not get or parse 'Parameters' port. Error: " << params.error() << std::endl;
        }

        message["Uuid"] = current_uuid_;
        return message;
    }
    std::string getFormattedTopic(const std::string &pattern)
    {
        std::vector<std::string> replacements;
        BT::Expected<std::string> station = getInput<std::string>("Entity");
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
        // Check if the message is valid
        // Use mutex to protect shared state
        {
            std::lock_guard<std::mutex> lock(mutex_);
            // Update state based on message content
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
};