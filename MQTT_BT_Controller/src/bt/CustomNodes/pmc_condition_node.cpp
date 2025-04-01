#include "bt/CustomNodes/pmc_condition_node.h"
#include "mqtt/subscription_manager.h"
#include "common_constants.h"

PMCConditionNode::PMCConditionNode(const std::string &name, const BT::NodeConfig &config, Proxy &bt_proxy)
    : MqttConditionNode(name, config, bt_proxy,
                        UNS_TOPIC + "/Planar",
                        "../schemas/weigh.schema.json")
{
    if (MqttNodeBase::subscription_manager_)
    {
        MqttNodeBase::subscription_manager_->registerDerivedInstance(this);
    }
}

BT::PortsList PMCConditionNode::providedPorts()
{
    return {
        BT::InputPort<std::string>("field_name", "Name of the field to monitor in the MQTT message"),
        BT::InputPort<std::string>("comparison_type", "Type of comparison: equal, not_equal, greater, less, contains"),
        BT::InputPort<std::string>("expected_value", "Value to compare against")};
}

bool PMCConditionNode::isInterestedIn(const std::string &field, const json &value)
{
    // Either call the parent implementation:
    auto field_name_res = getInput<std::string>("field_name");

    // First check if we have a valid field_name
    if (!field_name_res)
    {
        std::cout << "PMCConditionNode: No field_name input available" << std::endl;
        return false;
    }
    if (field == field_name_res.value())
    {
        return true;
    }
    return false;
}

void PMCConditionNode::callback(const json &msg, mqtt::properties props)
{
    std::lock_guard<std::mutex> lock(value_mutex_);
    {
        latest_msg_ = msg;
    }
}

BT::NodeStatus PMCConditionNode::tick()
{
    // Get the field name from inputs
    auto field_name_res = getInput<std::string>("field_name");
    if (!field_name_res)
    {
        std::cout << "MqttConditionNode: Missing field_name" << std::endl;
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
    std::lock_guard<std::mutex> lock(value_mutex_);
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