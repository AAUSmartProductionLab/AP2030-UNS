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

class AsyncMQTTReq : public BT::ThreadedAction
{
public:
    AsyncMQTTReq(const std::string &name, const BT::NodeConfig &config, Proxy &bt_proxy) : BT::ThreadedAction(name, config), bt_proxy_(bt_proxy)
    {
        // TODO base topic should probably be passed along
        topic_ptr_ = std::make_shared<Request>(BASE_TOPIC + "/PMC", "../schemas/connection.schema.json", "../schemas/response_state.schema.json", 1, std::bind(&ConnectToPMC::callback, this, std::placeholders::_1, std::placeholders::_2));
        if (bt_proxy_.is_connected())
        {
            // TODO this should wait until the proxy is connected
            topic_ptr_->register_callback(bt_proxy);
            topic_ptr_->subscribe(bt_proxy);
        }
    }
    static BT::PortsList providedPorts()
    {
        return {};
    }

    void callback(const json &msg, mqtt::properties props)
    {
        if (msg["state"] == "failure")
        {
            std::cout << "Failure" << std::endl;
            state = BT::NodeStatus::FAILURE;
        }
        else if (msg["state"] == "successful")
        {
            std::cout << "successful" << std::endl;
            state = BT::NodeStatus::SUCCESS;
        }
        else if (msg["state"] == "running")
        {
            std::cout << "running" << std::endl;
            state = BT::NodeStatus::RUNNING;
        }
    }

    BT::NodeStatus tick() override
    {
        if (state != BT::NodeStatus::RUNNING)
        {
            try
            {
                json message;
                // TODO this should perhaps come from a port or be defined during construction
                message["address"] = "127.0.0.1";
                message["target_state"] = "connected";
                message["xbot_no"] = 3;
                topic_ptr_->publish(bt_proxy_, message);
                state = BT::NodeStatus::RUNNING;
            }
            catch (...)
            {
                std::cout << "Exception" << std::endl;
                state = BT::NodeStatus::FAILURE;
            }
        }

        return state;
    }

private:
    std::shared_ptr<Topic> topic_ptr_;
    Proxy &bt_proxy_;
    BT::NodeStatus state;
    bool halted;
};
