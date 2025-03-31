#include "bt/mqtt_condition_node.h"
#include "mqtt/subscription_manager.h"
#include "common_constants.h"
#include <iostream>

// Initialize the static member
SubscriptionManager *MqttValueComparisonCondition::subscription_manager_ = nullptr;

MqttValueComparisonCondition::MqttValueComparisonCondition(const std::string &name,
                                                           const BT::NodeConfig &config,
                                                           Proxy &proxy,
                                                           const std::string &uns_topic,
                                                           const std::string &response_schema_path)
    : BT::ConditionNode(name, config),
      proxy_(proxy),
      uns_topic_(UNS_TOPIC),
      response_schema_path_(response_schema_path)
{
    // Get the field name from inputs
    auto field_name_res = getInput<std::string>("field_name");
    if (field_name_res)
    {
        field_name_ = field_name_res.value();
    }
    else
    {
        throw BT::RuntimeError("Missing required input [field_name]");
    }

    // Register with subscription manager
    if (subscription_manager_)
    {
        subscription_manager_->registerDerivedInstance<MqttValueComparisonCondition>(this);
    }
}

MqttValueComparisonCondition::~MqttValueComparisonCondition()
{
    // Optional cleanup
}

BT::PortsList MqttValueComparisonCondition::providedPorts()
{
    return {
        BT::InputPort<std::string>("field_name", "Name of the field to monitor in the MQTT message"),
        BT::InputPort<std::string>("comparison_type", "Type of comparison: equal, not_equal, greater, less, contains"),
        BT::InputPort<std::string>("expected_value", "Value to compare against")};
}

BT::NodeStatus MqttValueComparisonCondition::tick()
{
    // Get the comparison type from inputs
    auto comparison_type_res = getInput<std::string>("comparison_type");
    std::string comparison_type = "equal"; // Default
    if (comparison_type_res)
    {
        comparison_type = comparison_type_res.value();
    }

    // Get the expected value from the input port
    auto expected_value_res = getInput<std::string>("expected_value");
    if (!expected_value_res)
    {
        std::cout << "MqttValueComparisonCondition: Missing expected value" << std::endl;
        return BT::NodeStatus::FAILURE; // No expected value provided
    }

    std::string expected_str = expected_value_res.value();

    // Lock to safely access the latest value
    std::lock_guard<std::mutex> lock(value_mutex_);

    if (latest_value_.empty() || !latest_value_.contains(field_name_))
    {
        std::cout << "MqttValueComparisonCondition: No data or field not found: " << field_name_ << std::endl;
        return BT::NodeStatus::FAILURE; // No data or field not found
    }

    // Get the actual value
    json actual_value = latest_value_[field_name_];

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

void MqttValueComparisonCondition::handleMessage(const json &msg, mqtt::properties props)
{
    // Update the latest value
    std::lock_guard<std::mutex> lock(value_mutex_);
    latest_value_ = msg;

    // Debug output
    std::cout << "MqttValueComparisonCondition received message for field: " << field_name_ << std::endl;
}

bool MqttValueComparisonCondition::isInterestedIn(const std::string &field, const json &value)
{
    // We're interested in messages containing our monitored field
    return field == field_name_;
}

void MqttValueComparisonCondition::setSubscriptionManager(SubscriptionManager *manager)
{
    subscription_manager_ = manager;
}