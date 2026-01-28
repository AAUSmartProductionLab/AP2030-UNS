#include "bt/conditions/generic_condition_node.h"
#include "mqtt/node_message_distributor.h"
#include "aas/aas_interface_cache.h"
#include "utils.h"
#include <chrono>
#include <iomanip>
#include <thread>

// Helper to get current timestamp for logging
static std::string getLogTimestamp()
{
    auto now = std::chrono::system_clock::now();
    auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(now.time_since_epoch()) % 1000;
    auto time = std::chrono::system_clock::to_time_t(now);
    std::tm tm = *std::localtime(&time);
    std::ostringstream oss;
    oss << std::put_time(&tm, "%H:%M:%S") << '.' << std::setfill('0') << std::setw(3) << ms.count();
    return oss.str();
}

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
            std::cerr << "[" << getLogTimestamp() << "] [DataCondition] Node '" << this->name() 
                      << "' has no Asset input configured" << std::endl;
            return;
        }

        std::string asset_id = asset_input.value();

        auto property_name = getInput<std::string>("Property");
        if (!property_name.has_value())
        {
            std::cerr << "[" << getLogTimestamp() << "] [DataCondition] Node '" << this->name() 
                      << "' has no Property input configured" << std::endl;
            return;
        }

        // Check if we're already initialized for this specific asset and property
        // This handles the case where blackboard variables change between ticks
        if (topics_initialized_ &&
            asset_id == initialized_asset_id_ &&
            property_name.value() == initialized_property_)
        {
            return; // Already initialized for this asset/property combination
        }

        // If asset or property changed, we need to reinitialize
        if (topics_initialized_ &&
            (asset_id != initialized_asset_id_ || property_name.value() != initialized_property_))
        {
            std::cout << "[" << getLogTimestamp() << "] [DataCondition] Node '" << this->name() 
                      << "' reinitializing: asset/property changed from "
                      << initialized_asset_id_ << "/" << initialized_property_ << " to "
                      << asset_id << "/" << property_name.value() << std::endl;
            topics_initialized_ = false;
            latest_msg_ = json(); // Clear old message from different asset
            tick_count_ = 0;
            first_message_received_time_.reset();
        }

        std::cout << "[" << getLogTimestamp() << "] [DataCondition] Node '" << this->name() 
                  << "' INITIALIZING for Asset: " << asset_id 
                  << ", Property: " << property_name.value() << std::endl;
        
        initialization_time_ = std::chrono::steady_clock::now();

        // First, try to use the cached interface (fast path)
        auto cache = MqttSubBase::getAASInterfaceCache();
        if (cache)
        {
            auto cached_interface = cache->getInterface(asset_id, property_name.value(), "output");
            if (cached_interface.has_value())
            {
                std::cout << "[" << getLogTimestamp() << "] [DataCondition] Node '" << this->name() 
                          << "' using cached interface for property: " << property_name.value() 
                          << ", topic: " << cached_interface.value().getTopic() << std::endl;
                MqttSubBase::setTopic("output", cached_interface.value());
                topics_initialized_ = true;
                initialized_asset_id_ = asset_id;
                initialized_property_ = property_name.value();
                return;
            }
        }

        // Fall back to direct AAS query (slow path)
        std::cout << "[" << getLogTimestamp() << "] [DataCondition] Node '" << this->name() 
                  << "' falling back to direct AAS query" << std::endl;
        auto condition_opt = aas_client_.fetchInterface(asset_id, property_name.value(), "output");

        if (!condition_opt.has_value())
        {
            std::cerr << "[" << getLogTimestamp() << "] [DataCondition] FAILED to fetch interface from AAS for node: " 
                      << this->name() << std::endl;
            return;
        }

        std::cout << "[" << getLogTimestamp() << "] [DataCondition] Node '" << this->name() 
                  << "' got topic from AAS: " << condition_opt.value().getTopic() << std::endl;
        MqttSubBase::setTopic("output", condition_opt.value());
        topics_initialized_ = true;
        initialized_asset_id_ = asset_id;
        initialized_property_ = property_name.value();
    }
    catch (const std::exception &e)
    {
        std::cerr << "[" << getLogTimestamp() << "] [DataCondition] Exception initializing topics from AAS: " 
                  << e.what() << std::endl;
    }
}

BT::NodeStatus GenericConditionNode::tick()
{
    tick_count_++;
    
    // Ensure lazy initialization is done
    if (!ensureInitialized())
    {
        auto asset = getInput<std::string>("Asset");
        auto property = getInput<std::string>("Property");
        std::cerr << "[" << getLogTimestamp() << "] [DataCondition] Node '" << this->name() 
                  << "' tick #" << tick_count_ << " FAILED - could not initialize. "
                  << "Asset=" << (asset.has_value() ? asset.value() : "<not set>") << ", "
                  << "Property=" << (property.has_value() ? property.value() : "<not set>") << std::endl;
        return BT::NodeStatus::FAILURE;
    }

    // Calculate time since initialization for debugging
    auto now = std::chrono::steady_clock::now();
    auto ms_since_init = std::chrono::duration_cast<std::chrono::milliseconds>(now - initialization_time_).count();

    // Use a unique_lock since we may need to wait on a condition variable
    std::unique_lock<std::mutex> lock(mutex_);

    // Check if we have received a message yet
    if (latest_msg_.is_null())
    {
        // On early ticks, wait briefly for the first message to arrive
        // This handles the race condition between subscription and retained message delivery
        constexpr int MAX_WAIT_TICKS = 5;
        constexpr auto WAIT_TIMEOUT = std::chrono::milliseconds(200);
        
        if (tick_count_ <= MAX_WAIT_TICKS)
        {
            std::cout << "[" << getLogTimestamp() << "] [DataCondition] Node '" << this->name() 
                      << "' tick #" << tick_count_ << " - no message yet, waiting up to " 
                      << WAIT_TIMEOUT.count() << "ms for first message..." << std::endl;
            
            // Release lock and wait for message to arrive
            lock.unlock();
            
            // Wait in small increments, checking for message
            auto wait_start = std::chrono::steady_clock::now();
            while (std::chrono::steady_clock::now() - wait_start < WAIT_TIMEOUT)
            {
                std::this_thread::sleep_for(std::chrono::milliseconds(10));
                
                std::lock_guard<std::mutex> check_lock(mutex_);
                if (!latest_msg_.is_null())
                {
                    auto wait_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
                        std::chrono::steady_clock::now() - wait_start).count();
                    std::cout << "[" << getLogTimestamp() << "] [DataCondition] Node '" << this->name() 
                              << "' message arrived after " << wait_ms << "ms wait" << std::endl;
                    break;
                }
            }
            
            // Re-acquire lock and check again
            lock.lock();
        }
        
        // If still no message after waiting
        if (latest_msg_.is_null())
        {
            std::cerr << "[" << getLogTimestamp() << "] [DataCondition] Node '" << this->name() 
                      << "' tick #" << tick_count_ << " FAILURE - no message received!"
                      << " Time since init: " << ms_since_init << "ms"
                      << ", Asset: " << initialized_asset_id_
                      << ", Property: " << initialized_property_ << std::endl;
            
            // Log topics we're subscribed to
            for (const auto& [key, topic] : topics_)
            {
                std::cerr << "[" << getLogTimestamp() << "] [DataCondition]   -> Subscribed topic[" << key << "]: " 
                          << topic.getTopic() << std::endl;
            }
            
            return BT::NodeStatus::FAILURE;
        }
    }
    
    BT::Expected<std::string> field_name_res = getInput<std::string>("Field");
    BT::Expected<std::string> expected_value_res = getInput<std::string>("expected_value");
    BT::Expected<std::string> comparison_type_res = getInput<std::string>("comparison_type");

    if (field_name_res.has_value() && expected_value_res.has_value() && comparison_type_res.has_value())
    {
        bool result = compare(latest_msg_, field_name_res.value(), comparison_type_res.value(), expected_value_res.value());
        
        // Log comparison details on first few ticks or when result changes
        if (tick_count_ <= 3 || result != last_comparison_result_)
        {
            std::cout << "[" << getLogTimestamp() << "] [DataCondition] Node '" << this->name() 
                      << "' tick #" << tick_count_ << ": comparing " << field_name_res.value()
                      << " (" << comparison_type_res.value() << ") '" << expected_value_res.value() << "'"
                      << " -> actual: " << (latest_msg_.contains(field_name_res.value()) ? 
                                            latest_msg_[field_name_res.value()].dump() : "<missing>")
                      << " -> result: " << (result ? "SUCCESS" : "FAILURE")
                      << ", ms_since_init: " << ms_since_init << std::endl;
            last_comparison_result_ = result;
        }
        
        if (result)
        {
            return BT::NodeStatus::SUCCESS;
        }
    }
    else
    {
        std::cerr << "[" << getLogTimestamp() << "] [DataCondition] Node '" << this->name() 
                  << "' tick #" << tick_count_ << " FAILURE - missing input ports: "
                  << "Field=" << (field_name_res.has_value() ? field_name_res.value() : "<not set>")
                  << ", expected_value=" << (expected_value_res.has_value() ? expected_value_res.value() : "<not set>")
                  << ", comparison_type=" << (comparison_type_res.has_value() ? comparison_type_res.value() : "<not set>")
                  << std::endl;
    }
    return BT::NodeStatus::FAILURE;
}

void GenericConditionNode::callback(const std::string &topic_key, const json &msg, mqtt::properties props)
{
    BT::Expected<std::string> field_name_res = getInput<std::string>("Field");
    if (field_name_res && msg.contains(field_name_res.value()))
    {
        std::lock_guard<std::mutex> lock(mutex_);
        
        bool is_first_message = latest_msg_.is_null();
        latest_msg_ = msg;
        
        if (is_first_message)
        {
            first_message_received_time_ = std::chrono::steady_clock::now();
            auto ms_since_init = std::chrono::duration_cast<std::chrono::milliseconds>(
                first_message_received_time_.value() - initialization_time_).count();
            
            std::cout << "[" << getLogTimestamp() << "] [DataCondition] Node '" << this->name() 
                      << "' FIRST MESSAGE RECEIVED on topic_key='" << topic_key << "'"
                      << ", " << ms_since_init << "ms after init"
                      << ", tick_count at receipt: " << tick_count_
                      << ", Field=" << field_name_res.value()
                      << ", Value=" << msg[field_name_res.value()].dump() << std::endl;
        }
    }
    else
    {
        std::cout << "[" << getLogTimestamp() << "] [DataCondition] Node '" << this->name() 
                  << "' received message on topic_key='" << topic_key << "' but field '"
                  << (field_name_res.has_value() ? field_name_res.value() : "<not set>")
                  << "' not found in message. Keys: ";
        for (auto it = msg.begin(); it != msg.end(); ++it)
        {
            std::cout << it.key() << " ";
        }
        std::cout << std::endl;
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