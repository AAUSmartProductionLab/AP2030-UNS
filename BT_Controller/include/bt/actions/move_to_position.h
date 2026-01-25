#pragma once

#include "bt/mqtt_action_node.h"
#include <behaviortree_cpp/bt_factory.h>
#include <nlohmann/json.hpp>
#include <string>

/**
 * @brief MoveToPosition action node for moving assets to specified coordinates.
 * 
 * This node supports the $aas{} syntax for fetching position values directly
 * from AAS properties. Position values can be:
 *   - Literal values: x="1.5"
 *   - Blackboard references: x="{my_x_value}"  
 *   - AAS references: x="$aas{FillingLineAAS/HierarchicalStructures/EntryNode/Dispensing/Location/x}"
 * 
 * The path format follows basyx ModelReference structure:
 *   "AAS_ID/SubmodelIdShort/SMC1/.../PropertyIdShort"
 * 
 * Example XML usage:
 * @code
 * <MoveToPosition 
 *     Asset="{Xbot}"
 *     x="$aas{FillingLineAAS/HierarchicalStructures/EntryNode/{Station}/Location/x}"
 *     y="$aas{FillingLineAAS/HierarchicalStructures/EntryNode/{Station}/Location/y}"
 *     yaw="$aas{FillingLineAAS/HierarchicalStructures/EntryNode/{Station}/Location/theta}"
 *     Uuid="{ProductID}"
 * />
 * @endcode
 * 
 * Note: {Station} in the path is substituted from the blackboard before AAS lookup.
 */
class MoveToPosition : public MqttActionNode
{
private:
    std::string getFormattedTopic(const std::string &pattern, const BT::NodeConfig &config);

public:
    MoveToPosition(
        const std::string &name,
        const BT::NodeConfig &config,
        MqttClient &mqtt_client,
        AASClient &aas_client) : MqttActionNode(name, config, mqtt_client, aas_client) {}

    static BT::PortsList providedPorts();
    void initializeTopicsFromAAS() override;
    void onHalted() override;
    nlohmann::json createMessage() override;
};