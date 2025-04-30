#include "bt/CustomNodes/generic_condition_node.h"
#include "mqtt/node_message_distributor.h"
#include "mqtt/utils.h"

GenericConditionNode::GenericConditionNode(const std::string &name, const BT::NodeConfig &config, MqttClient &bt_mqtt_client,
                                           const std::string &response_topic, const std::string &response_schema_path, const int &subqos)
    : MqttSyncSubNode(name, config, bt_mqtt_client, response_topic, response_schema_path, subqos)
{
    response_topic_ = getFormattedTopic(response_topic_pattern_, config);
    if (MqttSubBase::node_message_distributor_)
    {
        MqttSubBase::node_message_distributor_->registerDerivedInstance(this);
    }
}

BT::PortsList GenericConditionNode::providedPorts()
{
    return {
        BT::details::PortWithDefault<std::string>(
            BT::PortDirection::INPUT,
            "Station",
            "{Station}",
            "The station from which to receive a message"),
        BT::InputPort<std::string>("Message", "The message from the station"),
        BT::InputPort<std::string>("Field", "Name of the field to monitor in the MQTT message"),
        BT::InputPort<std::string>("comparison_type", "Type of comparison: equal, not_equal, greater, less, contains"),
        BT::InputPort<std::string>("expected_value", "Value to compare against")};
}
std::string GenericConditionNode::getFormattedTopic(const std::string &pattern, const BT::NodeConfig &config)
{
    std::vector<std::string> replacements;
    BT::Expected<std::string> station = getInput<std::string>("Station");
    BT::Expected<std::string> message = getInput<std::string>("Message");
    if (station.has_value() && message.has_value())
    {
        replacements.push_back(station.value());
        replacements.push_back(message.value());
        return mqtt_utils::formatWildcardTopic(pattern, replacements);
    }
    return pattern;
}
bool GenericConditionNode::isInterestedIn(const json &msg)
{
    // Either call the parent implementation:
    auto field_name_res = getInput<std::string>("Field");

    // First check if we have a valid field_name
    if (!field_name_res)
    {
        std::cout << "GenericConditionNode: No Field input available" << std::endl;
        return false;
    }
    if (msg.contains(field_name_res.value()))
    {
        return true;
    }
    return false;
}

void GenericConditionNode::callback(const json &msg, mqtt::properties props)
{
    std::lock_guard<std::mutex> lock(mutex_);
    {
        latest_msg_ = msg;
    }
}

BT::NodeStatus GenericConditionNode::tick()
{
    // Get the field name from inputs
    auto field_name_res = getInput<std::string>("Field");
    if (!field_name_res)
    {
        std::cout << "MqttConditionNode: Missing Field" << std::endl;
        return BT::NodeStatus::FAILURE;
    }
    std::string field_name = field_name_res.value();

    auto comparison_type_res = getInput<std::string>("comparison_type");
    std::string comparison_type = "equal";
    if (comparison_type_res)
    {
        comparison_type = comparison_type_res.value();
    }
    // Get the expected value from the input port
    auto expected_value_res = getInput<std::string>("expected_value");
    if (!expected_value_res)
    {
        std::cout << "MqttConditionNode: Missing expected value" << std::endl;
        return BT::NodeStatus::FAILURE; // No expected value provided
    }

    std::string expected_str = expected_value_res.value();

    // Lock to safely access the latest value
    std::lock_guard<std::mutex> lock(mutex_);
    if (latest_msg_.empty() || !latest_msg_.contains(field_name)) // Use the local variable here
    {
        return BT::NodeStatus::FAILURE; // No data or field not found
    }

    // Get the actual value
    json actual_value = latest_msg_[field_name]; // And here

    bool result = false;

    // Handle different comparison types
    if (comparison_type == "equal")
    {
        // Handle different JSON types appropriately
        if (actual_value.is_string())
        {
            result = (actual_value.get<std::string>() == expected_str);
        }
        else if (actual_value.is_number())
        {
            try
            {
                double expected_num = std::stod(expected_str);
                result = (std::abs(actual_value.get<double>() - expected_num) < 1e-6);
            }
            catch (...)
            {
                result = false;
            }
        }
        else if (actual_value.is_boolean())
        {
            result = ((expected_str == "true" && actual_value.get<bool>()) ||
                      (expected_str == "false" && !actual_value.get<bool>()));
        }
        else
        {
            // For complex types, compare string representations
            result = (actual_value.dump() == expected_str);
        }
    }
    else if (comparison_type == "not_equal")
    {
        if (actual_value.is_string())
        {
            result = (actual_value.get<std::string>() != expected_str);
        }
        else if (actual_value.is_number())
        {
            try
            {
                double expected_num = std::stod(expected_str);
                result = (std::abs(actual_value.get<double>() - expected_num) >= 1e-6);
            }
            catch (...)
            {
                result = true;
            }
        }
        else
        {
            result = (actual_value.dump() != expected_str);
        }
    }
    else if (comparison_type == "greater")
    {
        if (actual_value.is_number())
        {
            try
            {
                double expected_num = std::stod(expected_str);
                result = (actual_value.get<double>() > expected_num);
            }
            catch (...)
            {
                result = false;
            }
        }
        else if (actual_value.is_string())
        {
            result = (actual_value.get<std::string>() > expected_str);
        }
    }
    else if (comparison_type == "less")
    {
        if (actual_value.is_number())
        {
            try
            {
                double expected_num = std::stod(expected_str);
                result = (actual_value.get<double>() < expected_num);
            }
            catch (...)
            {
                result = false;
            }
        }
        else if (actual_value.is_string())
        {
            result = (actual_value.get<std::string>() < expected_str);
        }
    }
    else if (comparison_type == "contains")
    {
        if (actual_value.is_string())
        {
            result = (actual_value.get<std::string>().find(expected_str) != std::string::npos);
        }
        else
        {
            std::string actual_str = actual_value.dump();
            result = (actual_str.find(expected_str) != std::string::npos);
        }
    }

    return result ? BT::NodeStatus::SUCCESS : BT::NodeStatus::FAILURE;
}