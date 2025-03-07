#pragma once

#include <mutex>
#include <atomic>
#include <functional>
#include <behaviortree_cpp/action_node.h>
#include <nlohmann/json.hpp>
#include "mqtt/mqtttopic.h"
#include "mqtt/proxy.h"

using nlohmann::json;

/**
 * @brief Base class for MQTT-based behavior tree action nodes
 *
 * This class implements common functionality for action nodes that communicate
 * with external systems using MQTT. It handles subscription, callbacks, state tracking
 * and the behavior tree action node lifecycle.
 */
class MqttActionNode : public BT::StatefulActionNode
{
protected:
    Request topic;
    Proxy &bt_proxy_;
    BT::NodeStatus state;
    std::mutex state_mutex_;
    std::atomic<bool> state_updated_{false};

public:
    /**
     * @brief Constructor
     *
     * @param name The node name in the behavior tree
     * @param config The node configuration
     * @param bt_proxy Reference to the MQTT proxy
     * @param topic_base Base topic for MQTT communication
     * @param pub_schema_path Path to the JSON schema for publishing
     * @param sub_schema_path Path to the JSON schema for subscription
     * @param qos MQTT quality of service level
     */
    MqttActionNode(const std::string &name,
                   const BT::NodeConfig &config,
                   Proxy &bt_proxy,
                   const std::string &topic_base,
                   const std::string &pub_schema_path,
                   const std::string &sub_schema_path,
                   int qos = 1);

    /**
     * @brief Define ports provided by this node type
     *
     * @return Port configuration
     */
    static BT::PortsList providedPorts();

    /**
     * @brief MQTT message callback
     *
     * @param msg JSON message received via MQTT
     * @param props MQTT message properties
     */
    void callback(const json &msg, mqtt::properties props);

    /**
     * @brief Create the message payload to be published
     *
     * This is a pure virtual method that must be implemented by derived classes
     * to create the specific message payload for each action.
     *
     * @return JSON message to publish
     */
    virtual json createMessage() = 0;

    /**
     * @brief Called when the node is activated
     *
     * @return Initial node status
     */
    BT::NodeStatus onStart() override;

    /**
     * @brief Called while the node is in the running state
     *
     * @return Current node status
     */
    BT::NodeStatus onRunning() override;

    /**
     * @brief Called when the node is halted
     */
    void onHalted() override;
};

/**
 * @brief Action node for moving a shuttle
 */
class MoveShuttle : public MqttActionNode
{
public:
    /**
     * @brief Constructor
     */
    MoveShuttle(const std::string &name, const BT::NodeConfig &config, Proxy &bt_proxy);

    /**
     * @brief Create the message payload for shuttle movement
     *
     * @return JSON message with shuttle movement parameters
     */
    json createMessage() override;
};

/**
 * @brief Action node for connecting to a PMC (Power Motion Controller)
 */
class ConnectToPMC : public MqttActionNode
{
public:
    /**
     * @brief Constructor
     */
    ConnectToPMC(const std::string &name, const BT::NodeConfig &config, Proxy &bt_proxy);

    /**
     * @brief Create the message payload for PMC connection
     *
     * @return JSON message with connection parameters
     */
    json createMessage() override;
};