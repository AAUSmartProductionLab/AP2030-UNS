#include <iostream>
#include <chrono>
#include <behaviortree_cpp/action_node.h>
#include <behaviortree_cpp/bt_factory.h>
#include <behaviortree_cpp/loggers/groot2_publisher.h>
#include <functional>
#include <nlohmann/json.hpp>
#include <nlohmann/json-schema.hpp>
#include "MQTT_classes.cpp"

const std::string BROKER_URI("192.168.0.104:1883");
const std::string CLIENT_ID("behavior_tree");
const std::string BASE_TOPIC("IMATile");

using nlohmann::json;
using nlohmann::json_schema::json_validator;
class MoveShuttle : public BT::StatefulActionNode
{
public:
    MoveShuttle(const std::string &name, const BT::NodeConfig &config, Proxy &bt_proxy) : BT::StatefulActionNode(name, config), bt_proxy_(bt_proxy), topic(BASE_TOPIC + "/PMC", "../schemas/moveToPosition.schema.json", "../schemas/response_state.schema.json", 1, std::bind(&MoveShuttle::callback, this, std::placeholders::_1, std::placeholders::_2))
    {
        // TODO base topic should probably be passed along
        std::cout << "Ticked" << std::endl;
        if (bt_proxy_.is_connected())
        {
            // TODO this should wait until the proxy is connected
            topic.register_callback(bt_proxy);
            topic.subscribe(bt_proxy);
        }
    }
    static BT::PortsList providedPorts()
    {
        return {};
    }
    void callback(const json &msg, mqtt::properties props)
    {
        // TODO needs to parse the json
        std::cout << "Connect Callback received message: " << msg.dump() << std::endl;

        {
            std::lock_guard<std::mutex> lock(state_mutex_);
            if (msg["state"] == "failure")
            {
                std::cout << "Failure" << std::endl;
                state = BT::NodeStatus::FAILURE;
            }
            else if (msg["state"] == "successful")
            {
                state = BT::NodeStatus::SUCCESS;
                std::cout << state << "This should be the state" << std::endl;
            }
            else if (msg["state"] == "running")
            {
                state = BT::NodeStatus::RUNNING;
            }
        }
        state_updated_ = true;
    }

    BT::NodeStatus onStart() override
    {
        std::cout << "Ticked" << std::endl;
        try
        {
            json message;
            // TODO this should perhaps come from a port or be defined during construction
            message["xbot_id"] = 1;
            message["target_pos"] = "loading";
            topic.publish(bt_proxy_, message);
            state = BT::NodeStatus::RUNNING;
        }
        catch (...)
        {
            std::cout << "Exception" << std::endl;
            state = BT::NodeStatus::FAILURE;
        }
        return state;
    }

    /// method invoked by an action in the RUNNING state.
    /// Keeps returning the current state
    BT::NodeStatus onRunning() override
    {
        std::lock_guard<std::mutex> lock(state_mutex_);
        std::cout << "Ticked, state: " << static_cast<int>(state) << ", updated: " << state_updated_ << std::endl;
        return state;
    }

    void onHalted() override
    {
        std::cout << "Ticked" << std::endl;
        /// TODO This should perhaps send a stop command to the PMC?
        std::cout
            << "Move node interrupted" << std::endl;
    }

private:
    Request topic;
    Proxy &bt_proxy_;
    BT::NodeStatus state;
    bool halted;
    std::mutex state_mutex_;
    std::atomic<bool> state_updated_{false};
};

class ConnectToPMC : public BT::StatefulActionNode
{
public:
    ConnectToPMC(const std::string &name, const BT::NodeConfig &config, Proxy &bt_proxy) : BT::StatefulActionNode(name, config), bt_proxy_(bt_proxy), topic(BASE_TOPIC + "/PMC", "../schemas/connection.schema.json", "../schemas/response_state.schema.json", 1, std::bind(&ConnectToPMC::callback, this, std::placeholders::_1, std::placeholders::_2))
    {
        // TODO base topic should probably be passed along
        if (bt_proxy_.is_connected())
        {
            // TODO this should wait until the proxy is connected
            topic.register_callback(bt_proxy);
            topic.subscribe(bt_proxy);
        }
    }
    static BT::PortsList providedPorts()
    {
        return {};
    }
    void callback(const json &msg, mqtt::properties props)
    {
        // TODO needs to parse the json
        std::cout << "Connect Callback received message: " << msg.dump() << std::endl;

        {
            std::lock_guard<std::mutex> lock(state_mutex_);
            if (msg["state"] == "failure")
            {
                std::cout << "Failure" << std::endl;
                state = BT::NodeStatus::FAILURE;
            }
            else if (msg["state"] == "successful")
            {
                state = BT::NodeStatus::SUCCESS;
                std::cout << state << "This should be the state" << std::endl;
            }
            else if (msg["state"] == "running")
            {
                state = BT::NodeStatus::RUNNING;
            }
        }
        state_updated_ = true;
    }

    BT::NodeStatus onStart() override
    {
        try
        {
            json message;
            // TODO this should perhaps come from a port or be defined during construction

            message["address"] = "127.0.0.1";
            message["target_state"] = "connected";
            message["xbot_no"] = 3;
            topic.publish(bt_proxy_, message);
            state = BT::NodeStatus::RUNNING;
        }
        catch (...)
        {
            std::cout << "Exception" << std::endl;
            state = BT::NodeStatus::FAILURE;
        }
        return state;
    }

    /// method invoked by an action in the RUNNING state.
    /// Keeps returning the current state
    BT::NodeStatus onRunning() override
    {
        std::lock_guard<std::mutex> lock(state_mutex_);
        std::cout << "Ticked, state: " << static_cast<int>(state) << ", updated: " << state_updated_ << std::endl;
        return state;
    }

    void onHalted() override
    {
        /// TODO This should perhaps send a stop command to the PMC?
        std::cout
            << "Move node interrupted" << std::endl;
    }

private:
    Request topic;
    Proxy &bt_proxy_;
    BT::NodeStatus state;
    bool halted;
    std::mutex state_mutex_;
    std::atomic<bool> state_updated_{false};
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
    factory.registerNodeType<MoveShuttle>("MoveShuttle", std::ref(bt_proxy));
    auto tree = factory.createTreeFromFile("../src/bt_tree.xml");
    BT::Groot2Publisher publisher(tree);

    auto status = tree.tickOnce();
    while (status == BT::NodeStatus::RUNNING)
    {
        // Sleep to avoid busy loops.
        // do NOT use other sleep functions!
        // Small sleep time is OK, here we use a large one only to
        // have less messages on the console.
        std::cout << "ticked" << std::endl;
        tree.sleep(std::chrono::milliseconds(100));
        status = tree.tickOnce();
    }
    // while (std::tolower(std::cin.get()) != 'q')
    //     ;

    // // Disconnect

    // try
    // {
    //     std::cout << "\nDisconnecting from the MQTT server..." << std::flush;
    //     bt_proxy.disconnect()->wait();
    //     std::cout << "OK" << std::endl;
    // }
    // catch (const mqtt::exception &exc)
    // {
    //     std::cerr << exc << std::endl;
    //     return 1;
    // }

    return 0;
}