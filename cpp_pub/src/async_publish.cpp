#include <iostream>
#include <chrono>
#include <behaviortree_cpp/bt_factory.h>
#include <behaviortree_cpp/loggers/groot2_publisher.h>
#include <functional>
#include "bt/mqtt_action_node.h"

// Constants used throughout the application
const std::string BROKER_URI("192.168.0.104:1883");
const std::string CLIENT_ID("behavior_tree");
const std::string BASE_TOPIC("IMATile");

// MoveShuttle implementation

class ConnectToPMC : public MqttActionNode
{
public:
    ConnectToPMC(const std::string &name, const BT::NodeConfig &config, Proxy &bt_proxy) : MqttActionNode(name, config, bt_proxy,
                                                                                                          BASE_TOPIC + "/PMC",
                                                                                                          "../schemas/connection.schema.json",
                                                                                                          "../schemas/response_state.schema.json")
    {
    }
    json createMessage()
    {
        json message;
        message["address"] = "127.0.0.1";
        message["target_state"] = "connected";
        message["xbot_no"] = 3;
        return message;
    }
};

class MoveShuttleToLoading : public MqttActionNode
{
public:
    MoveShuttleToLoading(const std::string &name, const BT::NodeConfig &config, Proxy &bt_proxy) : MqttActionNode(name, config, bt_proxy,
                                                                                                                  BASE_TOPIC + "/PMC",
                                                                                                                  "../schemas/moveToPosition.schema.json",
                                                                                                                  "../schemas/response_state.schema.json")
    {
    }
    json createMessage()
    {
        json message;
        message["xbot_id"] = 1;
        message["target_pos"] = "loading";
        return message;
    }
};

class MoveShuttleToFilling : public MqttActionNode
{
public:
    MoveShuttleToFilling(const std::string &name, const BT::NodeConfig &config, Proxy &bt_proxy) : MqttActionNode(name, config, bt_proxy,
                                                                                                                  BASE_TOPIC + "/PMC",
                                                                                                                  "../schemas/moveToPosition.schema.json",
                                                                                                                  "../schemas/response_state.schema.json")
    {
    }
    json createMessage()
    {
        json message;
        message["xbot_id"] = 1;
        message["target_pos"] = "filling";
        return message;
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

    // BT stuff
    BT::BehaviorTreeFactory factory;
    factory.registerNodeType<ConnectToPMC>("ConnectToPMC", std::ref(bt_proxy));
    factory.registerNodeType<MoveShuttleToLoading>("MoveShuttleToLoading", std::ref(bt_proxy));
    factory.registerNodeType<MoveShuttleToFilling>("MoveShuttleToFilling", std::ref(bt_proxy));
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