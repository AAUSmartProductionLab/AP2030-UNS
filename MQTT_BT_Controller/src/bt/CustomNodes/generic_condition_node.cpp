#include "bt/CustomNodes/generic_condition_node.h"
#include "mqtt/node_message_distributor.h"
#include "mqtt/utils.h"

GenericConditionNode::GenericConditionNode(const std::string &name, const BT::NodeConfig &config, MqttClient &bt_mqtt_client,
                                           const mqtt_utils::Topic &response_topic)
    : MqttSyncSubNode(name, config, bt_mqtt_client, response_topic)
{
    response_topic_.setTopic(getFormattedTopic(response_topic.getPattern(), config));
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
        BT::InputPort<std::string>("expected_value", "Value to compare against"),
        BT::InputPort<int>("timeout_ms", "Timeout in milliseconds (default: 5000)")};
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
    latest_msg_ = msg;
    cv_.notify_one(); // Notify waiting threads that new data has arrived
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

    auto expected_value_res = getInput<std::string>("expected_value");
    if (!expected_value_res)
    {
        std::cout << "MqttConditionNode: Missing expected value" << std::endl;
        return BT::NodeStatus::FAILURE;
    }
    std::string expected_str = expected_value_res.value();

    // Optional timeout parameter
    BT::Expected<int> timeout_ms_res = getInput<int>("timeout_ms");
    if (timeout_ms_res)
    {
        timeout_ = std::chrono::milliseconds(timeout_ms_res.value());
    }

    // Lock and wait for data
    std::unique_lock<std::mutex> lock(mutex_);

    // Check if we need to wait for data
    if (latest_msg_.empty() || !latest_msg_.contains(field_name))
    {
        if (has_timed_out_)
        {
            // Reset timeout flag for next tick and return failure
            has_timed_out_ = false;
            return BT::NodeStatus::FAILURE;
        }

        // Wait for notification with timeout
        bool data_received = cv_.wait_for(lock, timeout_, [this, &field_name]()
                                          { return !latest_msg_.empty() && latest_msg_.contains(field_name); });

        if (!data_received)
        {
            has_timed_out_ = true;
            return BT::NodeStatus::RUNNING; // Still waiting for data
        }
    }

    // Now we have data, proceed with comparison
    json actual_value = latest_msg_[field_name];

    bool result = false;

    // Handle different comparison types
    if (comparison_type == "equal" || comparison_type == "not_equal")
    {
        // Handle different JSON types appropriately
        if (actual_value.is_string())
        {
            if (expected_str == "operational" && field_name == "State")
            {
                std::string state = actual_value.get<std::string>();
                result = (state == "IDLE" ||
                          state == "STARTING" ||
                          state == "EXECUTE" ||
                          state == "COMPLETING" ||
                          state == "COMPLETE" ||
                          state == "RESETTING" ||
                          state == "HOLDING" ||
                          state == "HELD" ||
                          state == "UNHOLDING" ||
                          state == "SUSPENDING" ||
                          state == "SUSPENDED" ||
                          state == "UNSUSPENDING");
            }
            else
            {
                result = (actual_value.get<std::string>() == expected_str);
            }
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

        // Invert the result if comparison_type is "not_equal"
        if (comparison_type == "not_equal")
        {
            result = !result;
        }
    }
    else if (comparison_type == "greater" || comparison_type == "less")
    {
        if (actual_value.is_number())
        {
            try
            {
                double expected_num = std::stod(expected_str);
                // Use greater-than by default, switch to less-than if needed
                if (comparison_type == "greater")
                {
                    result = (actual_value.get<double>() > expected_num);
                }
                else
                { // "less"
                    result = (actual_value.get<double>() < expected_num);
                }
            }
            catch (...)
            {
                result = false;
            }
        }
        else if (actual_value.is_string())
        {
            // Use greater-than by default, switch to less-than if needed
            if (comparison_type == "greater")
            {
                result = (actual_value.get<std::string>() > expected_str);
            }
            else
            { // "less"
                result = (actual_value.get<std::string>() < expected_str);
            }
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