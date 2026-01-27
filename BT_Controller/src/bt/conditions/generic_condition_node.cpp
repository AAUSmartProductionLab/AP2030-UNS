#include "bt/conditions/generic_condition_node.h"
#include "mqtt/node_message_distributor.h"
#include "aas/aas_interface_cache.h"
#include "utils.h"

BT::PortsList GenericConditionNode::providedPorts()
{
    return {
        BT::details::PortWithDefault<std::string>(
            BT::PortDirection::INPUT,
            "Asset",
            "{Asset}",
            "The Asset from which to receive a message"),
        BT::InputPort<std::string>("Property", "The property interface from the Asset"),
        BT::InputPort<std::string>("Field", "Name of the field to monitor in the MQTT message"),
        BT::InputPort<std::string>("comparison_type", "Type of comparison: equal, not_equal, greater, less, contains"),
        BT::InputPort<std::string>("expected_value", "Value to compare against")};
}

void GenericConditionNode::initializeTopicsFromAAS()
{
    try
    {
        auto asset_input = getInput<std::string>("Asset");
        if (!asset_input.has_value())
        {
            std::cerr << "Node '" << this->name() << "' has no Asset input configured" << std::endl;
            return;
        }

        std::string asset_id = asset_input.value();
        
        auto property_name = getInput<std::string>("Property");
        if (!property_name.has_value())
        {
            std::cerr << "Node '" << this->name() << "' has no Property input configured" << std::endl;
            return;
        }

        // Check if we're already initialized for this specific asset and property
        // This handles the case where blackboard variables change between ticks
        if (topics_initialized_ && 
            asset_id == initialized_asset_id_ && 
            property_name.value() == initialized_property_)
        {
            return;  // Already initialized for this asset/property combination
        }
        
        // If asset or property changed, we need to reinitialize
        if (topics_initialized_ && 
            (asset_id != initialized_asset_id_ || property_name.value() != initialized_property_))
        {
            std::cout << "Node '" << this->name() << "' reinitializing: asset/property changed from "
                      << initialized_asset_id_ << "/" << initialized_property_ << " to "
                      << asset_id << "/" << property_name.value() << std::endl;
            topics_initialized_ = false;
            latest_msg_ = json();  // Clear old message from different asset
        }

        std::cout << "Node '" << this->name() << "' initializing for Asset: " << asset_id << std::endl;

        // First, try to use the cached interface (fast path)
        auto cache = MqttSubBase::getAASInterfaceCache();
        if (cache)
        {
            auto cached_interface = cache->getInterface(asset_id, property_name.value(), "output");
            if (cached_interface.has_value())
            {
                std::cout << "Node '" << this->name() << "' using cached interface for property: " 
                          << property_name.value() << std::endl;
                MqttSubBase::setTopic("output", cached_interface.value());
                topics_initialized_ = true;
                initialized_asset_id_ = asset_id;
                initialized_property_ = property_name.value();
                return;
            }
        }

        // Fall back to direct AAS query (slow path)
        std::cout << "Node '" << this->name() << "' falling back to direct AAS query" << std::endl;
        auto condition_opt = aas_client_.fetchInterface(asset_id, property_name.value(), "output");

        if (!condition_opt.has_value())
        {
            std::cerr << "Failed to fetch interface from AAS for node: " << this->name() << std::endl;
            return;
        }

        MqttSubBase::setTopic("output", condition_opt.value());
        topics_initialized_ = true;
        initialized_asset_id_ = asset_id;
        initialized_property_ = property_name.value();
    }
    catch (const std::exception &e)
    {
        std::cerr << "Exception initializing topics from AAS: " << e.what() << std::endl;
    }
}

BT::NodeStatus GenericConditionNode::tick()
{
    // Ensure lazy initialization is done
    if (!ensureInitialized())
    {
        auto asset = getInput<std::string>("Asset");
        auto property = getInput<std::string>("Property");
        std::cerr << "Node '" << this->name() << "' FAILED - could not initialize. "
                  << "Asset=" << (asset.has_value() ? asset.value() : "<not set>") << ", "
                  << "Property=" << (property.has_value() ? property.value() : "<not set>") << std::endl;
        return BT::NodeStatus::FAILURE;
    }

    // Use a unique_lock since we need to wait on a condition variable
    std::unique_lock<std::mutex> lock(mutex_);

    // Wait until a message is received
    if (latest_msg_.is_null())
    {
        return BT::NodeStatus::FAILURE;
    }
    BT::Expected<std::string> field_name_res = getInput<std::string>("Field");
    BT::Expected<std::string> expected_value_res = getInput<std::string>("expected_value");
    BT::Expected<std::string> comparison_type_res = getInput<std::string>("comparison_type");

    if (field_name_res.has_value() && expected_value_res.has_value() && comparison_type_res.has_value())
    {
        bool result = compare(latest_msg_, field_name_res.value(), comparison_type_res.value(), expected_value_res.value());
        if (result)
        {
            return BT::NodeStatus::SUCCESS;
        }
    }
    return BT::NodeStatus::FAILURE;
}

void GenericConditionNode::callback(const std::string &topic_key, const json &msg, mqtt::properties props)
{
    BT::Expected<std::string> field_name_res = getInput<std::string>("Field");
    if (field_name_res && msg.contains(field_name_res.value()))
    {
        std::lock_guard<std::mutex> lock(mutex_);
        latest_msg_ = msg;
    }
    else
    {
        std::cout << "GenericConditionNode: No valid field name or message does not contain the field." << std::endl;
    }
}

bool GenericConditionNode::compare(const json &msg, const std::string &field_name, const std::string &comparison_type,
                                   const std::string &expected_str)
{
    bool result = false;

    json actual_value = msg[field_name];

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
                          state == "RESETTING");
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
    else if (comparison_type == "inside" || comparison_type == "outside")
    {
        // Parse the expected range values (format: "min;max")
        size_t delimiter_pos = expected_str.find(';');
        if (delimiter_pos != std::string::npos)
        {
            std::string min_str = expected_str.substr(0, delimiter_pos);
            std::string max_str = expected_str.substr(delimiter_pos + 1);

            if (actual_value.is_number())
            {
                try
                {
                    double min_val = std::stod(min_str);
                    double max_val = std::stod(max_str);
                    double actual_num = actual_value.get<double>();

                    // Check if the value is inside or outside the range
                    bool is_inside = (actual_num >= min_val && actual_num <= max_val);
                    result = (comparison_type == "inside") ? is_inside : !is_inside;
                }
                catch (...)
                {
                    std::cerr << "Error parsing number for inside/outside comparison" << std::endl;
                }
            }
        }
    }
    return result;
}