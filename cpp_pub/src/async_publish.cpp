#include <iostream>
#include <chrono>
#include <behaviortree_cpp/action_node.h>
#include <behaviortree_cpp/bt_factory.h>
#include <behaviortree_cpp/loggers/groot2_publisher.h>
#include <functional>
#include <nlohmann/json.hpp>
#include <nlohmann/json-schema.hpp>
#include "mqtt/utils.h"
#include "mqtt/callbacks.h"
#include "mqtt/mqtttopic.h"
#include "mqtt/proxy.h"

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
        // Debug entry point of callback
        std::cout << "Message received: " << msg.dump() << std::endl;

        // Use mutex to protect shared state
        {
            std::lock_guard<std::mutex> lock(state_mutex_);

            // Update state based on message content
            if (msg.contains("state"))
            {
                if (msg["state"] == "failure")
                {
                    std::cout << "State updated to FAILURE" << std::endl;
                    state = BT::NodeStatus::FAILURE;
                }
                else if (msg["state"] == "successful")
                {
                    std::cout << "State updated to SUCCESS" << std::endl;
                    state = BT::NodeStatus::SUCCESS;
                }
                else if (msg["state"] == "running")
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

    BT::NodeStatus onStart() override
    {
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

        // Use mutex for accessing shared state
        std::lock_guard<std::mutex> lock(state_mutex_);

        // Use explicit memory ordering when loading the flag
        bool updated = state_updated_.load(std::memory_order_acquire);
        if (updated)
        {
            // We got an update from the callback, reset the flag
            state_updated_.store(false, std::memory_order_seq_cst);

            // Return the updated state (SUCCESS/FAILURE/RUNNING)
            return state;
        }
        else
        {
            // No update received yet, continue in RUNNING state
            return BT::NodeStatus::RUNNING;
        }
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
        std::cout << "Message received: " << msg.dump() << std::endl;

        // Use mutex to protect shared state
        {
            std::lock_guard<std::mutex> lock(state_mutex_);

            // Update state based on message content
            if (msg.contains("state"))
            {
                if (msg["state"] == "failure")
                {
                    std::cout << "Failure" << std::endl;
                    state = BT::NodeStatus::FAILURE;
                }
                else if (msg["state"] == "successful")
                {
                    state = BT::NodeStatus::SUCCESS;
                    std::cout << "State updated to SUCCESS: " << static_cast<int>(state) << std::endl;
                }
                else if (msg["state"] == "running")
                {
                    state = BT::NodeStatus::RUNNING;
                    std::cout << "State updated to RUNNING" << std::endl;
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

        // Use mutex for accessing shared state
        std::lock_guard<std::mutex> lock(state_mutex_);

        // Use explicit memory ordering when loading the flag
        bool updated = state_updated_.load(std::memory_order_acquire);

        if (updated)
        {
            // We got an update from the callback, reset the flag
            state_updated_.store(false, std::memory_order_seq_cst);

            // Return the updated state (SUCCESS/FAILURE/RUNNING)
            return state;
        }
        else
        {
            // No update received yet, continue in RUNNING state
            return BT::NodeStatus::RUNNING;
        }
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