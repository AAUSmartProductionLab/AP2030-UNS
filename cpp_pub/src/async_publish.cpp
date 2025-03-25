#include <iostream>
#include <chrono>
#include <behaviortree_cpp/bt_factory.h>
#include <behaviortree_cpp/loggers/groot2_publisher.h>
#include <functional>
#include "bt/mqtt_action_node.h"
#include "bt/node_subscription_manager.h"
#include "mqtt/utils.h"

// Constants used throughout the application
const std::string BROKER_URI("192.168.0.104:1883");
const std::string CLIENT_ID("behavior_tree");
const std::string UNS_TOPIC("NN/Nybrovej/InnoLab/Planar");

// MoveShuttle implementation
struct Position2D
{
    double x;
    double y;
};

namespace BT
{
    template <>
    inline Position2D convertFromString(StringView str)
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

class MoveShuttleToPosition : public MqttActionNode
{
private:
    std::string current_command_uuid_;

public:
    MoveShuttleToPosition(const std::string &name, const BT::NodeConfig &config, Proxy &bt_proxy) : MqttActionNode(name, config, bt_proxy,
                                                                                                                   UNS_TOPIC,
                                                                                                                   "../schemas/moveToPosition.schema.json",
                                                                                                                   "../schemas/moveResponse.schema.json")
    {
        if (MqttActionNode::subscription_manager_)
        {
            MqttActionNode::subscription_manager_->registerDerivedInstance<MoveShuttleToPosition>(this);
        }
    }
    static BT::PortsList providedPorts()
    {
        return {BT::InputPort<Position2D>("goal"), BT::InputPort<int>("xbot_id")};
    }
    json createMessage()
    {
        BT::Expected<int> id = getInput<int>("xbot_id");
        BT::Expected<Position2D> goal = getInput<Position2D>("goal");

        json message;
        current_command_uuid_ = mqtt_utils::generate_uuid();
        message["XbotId"] = id.value();
        message["TargetPos"] = json::array({goal.value().x, goal.value().y});
        message["CommandUuid"] = current_command_uuid_;
        std::cout << current_command_uuid_ << std::endl;
        return message;
    }
    // Override isInterestedIn to filter messages
    bool isInterestedIn(const std::string &field, const json &value) override
    {
        if (field == "CommandUuid" && value.is_string())
        {
            bool interested = (value.get<std::string>() == current_command_uuid_);

            return interested;
        }
        return false;
    }

    void callback(const json &msg, mqtt::properties props) override
    {

        // Use mutex to protect shared state
        {
            std::lock_guard<std::mutex> lock(state_mutex_);

            // Update state based on message content
            if (msg.contains("state"))
            {
                if (msg["state"] == 0 || msg["state"] == 1 || msg["state"] == 4 || msg["state"] == 10 || msg["state"] == 14)
                {
                    std::cout << "State updated to FAILURE" << std::endl;
                    state = BT::NodeStatus::FAILURE;
                }
                else if (msg["state"] == 2 || msg["state"] == 3)
                {
                    std::cout << "State updated to SUCCESS" << std::endl;
                    state = BT::NodeStatus::SUCCESS;
                }
                else if (msg["state"] == 5 || msg["state"] == 6 || msg["state"] == 7 || msg["state"] == 8 || msg["state"] == 9)
                {
                    std::cout << "State updated to RUNNING" << std::endl;
                    state = BT::NodeStatus::RUNNING;
                }
                else
                {
                    std::cout << "Unknown state value: " << msg["state"] << std::endl;
                }

                // Use explicit memory ordering when setting the flag
                state_updated_.store(true, std::memory_order_seq_cst);
            }
            else
            {
                std::cout << "Message doesn't contain 'state' field" << std::endl;
            }
        }
    }
};

int main(int argc, char *argv[])
{
    std::string serverURI = (argc > 1) ? std::string{argv[1]} : BROKER_URI;
    std::string clientId = CLIENT_ID;
    int repetitions = 5;

    auto connOpts = mqtt::connect_options_builder::v5()
                        .clean_start(false)
                        .properties({{mqtt::property::SESSION_EXPIRY_INTERVAL, 604800}})
                        .finalize();

    Proxy bt_proxy(serverURI, clientId, connOpts, repetitions);

    NodeTypeSubscriptionManager subscription_manager(bt_proxy);
    MqttActionNode::setSubscriptionManager(&subscription_manager);

    subscription_manager.registerNodeType<MoveShuttleToPosition>(
        UNS_TOPIC,
        "../schemas/moveResponse.schema.json");

    // BT stuff
    BT::BehaviorTreeFactory factory;

    factory.registerNodeType<MoveShuttleToPosition>("MoveShuttleToPosition", std::ref(bt_proxy));
    auto tree = factory.createTreeFromFile("../src/bt_tree.xml");
    BT::Groot2Publisher publisher(tree);

    while (true)
    {
        // Tick the tree until it completes
        auto status = tree.tickOnce();
        while (status == BT::NodeStatus::RUNNING)
        {
            tree.sleep(std::chrono::milliseconds(100));
            status = tree.tickOnce();
            tree.tickWhileRunning();
        }

        // When tree completes (SUCCESS or FAILURE), print the result
        std::cout << "Behavior tree execution completed with status: "
                  << (status == BT::NodeStatus::SUCCESS ? "SUCCESS" : "FAILURE") << std::endl;

        std::cout << "====== Restarting behavior tree... ======" << std::endl;
        // Optional: Add a delay between tree executions
        std::this_thread::sleep_for(std::chrono::seconds(1));
    }

    return 0;
}