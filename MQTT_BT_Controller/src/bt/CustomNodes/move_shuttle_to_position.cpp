#include "bt/CustomNodes/move_shuttle_to_position.h"
#include "mqtt/utils.h"
#include "mqtt/subscription_manager.h"
#include "common_constants.h"

// BT template specialization implementation
namespace BT
{
    template <>
    Position2D convertFromString(StringView str)
    {
        // We expect real numbers separated by semicolons
        auto parts = splitString(str, ';');
        if (parts.size() != 2)
        {
            throw RuntimeError("invalid input)");
        }
        else
        {
            Position2D output;
            output.x = convertFromString<double>(parts[0]);
            output.y = convertFromString<double>(parts[1]);
            return output;
        }
    }
}

// MoveShuttleToPosition implementation
MoveShuttleToPosition::MoveShuttleToPosition(const std::string &name, const BT::NodeConfig &config, Proxy &bt_proxy, const std::string &request_topic, const std::string &response_topic, const std::string &request_schema_path, const std::string &response_schema_path)
    : MqttActionNode(name, config, bt_proxy,
                     request_topic, response_topic, request_schema_path, response_schema_path)
{
    if (MqttSubBase::subscription_manager_)
    {
        MqttSubBase::subscription_manager_->registerDerivedInstance(this);
    }
}

BT::PortsList MoveShuttleToPosition::providedPorts()
{
    return {BT::InputPort<Position2D>("goal"), BT::InputPort<int>("xbot_id")};
}

json MoveShuttleToPosition::createMessage()
{
    BT::Expected<int> id = getInput<int>("xbot_id");
    BT::Expected<Position2D> goal = getInput<Position2D>("goal");

    json message;
    current_command_uuid_ = mqtt_utils::generate_uuid();
    message["XbotId"] = id.value();
    message["TargetPos"] = json::array({goal.value().x, goal.value().y});
    message["CommandUuid"] = current_command_uuid_;
    return message;
}

bool MoveShuttleToPosition::isInterestedIn(const std::string &field, const json &value)
{

    if (field == "CommandUuid" && value.is_string())
    {
        bool interested = (value.get<std::string>() == current_command_uuid_);
        return interested;
    }
    return false;
}

void MoveShuttleToPosition::callback(const json &msg, mqtt::properties props)
{
    // Use mutex to protect shared state
    {
        std::lock_guard<std::mutex> lock(mutex_);

        // Update state based on message content
        if (msg.contains("State"))
        {
            if (msg["State"] == "ABORTED" || msg["State"] == "STOPPED")
            {
                current_command_uuid_ = "";
                // Change from setting internal state to updating node status
                setStatus(BT::NodeStatus::FAILURE);
                emitWakeUpSignal();
            }
            else if (msg["State"] == "COMPLETE")
            {
                current_command_uuid_ = "";
                // Change from setting internal state to updating node status
                setStatus(BT::NodeStatus::SUCCESS);
                emitWakeUpSignal();
            }
            else if (msg["State"] == "HELD" || msg["State"] == "SUSPENDED" || msg["State"] == "EXECUTED")
            {
                std::cout << "State is HELD, SUSPENDED or Executing" << std::endl;
                // No need to set RUNNING again if already running
                emitWakeUpSignal();
            }
            else
            {
                std::cout << "Unknown State value: " << msg["State"] << std::endl;
            }
        }
        else
        {
            std::cout << "Message doesn't contain 'state' field" << std::endl;
        }
    }
}