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
 *   - AAS references: x="$aas{SubmodelId/element/path}"
 * 
 * The path format follows basyx ModelReference structure (Submodel-first):
 *   "SubmodelId/SMC1/.../PropertyIdShort"
 * 
 * Example XML usage with AAS references:
 * @code
 * <!-- Dynamic station from blackboard - Station variable contains station idShort -->
 * <Script code="Station := 'Dispensing'" />
 * <MoveToPosition 
 *     Asset="{Xbot}"
 *     x="$aas{https://smartproductionlab.aau.dk/submodels/instances/aauFillingLineAAS/HierarchicalStructures/EntryNode/{Station}/Location/x}"
 *     y="$aas{https://smartproductionlab.aau.dk/submodels/instances/aauFillingLineAAS/HierarchicalStructures/EntryNode/{Station}/Location/y}"
 *     yaw="$aas{https://smartproductionlab.aau.dk/submodels/instances/aauFillingLineAAS/HierarchicalStructures/EntryNode/{Station}/Location/theta}"
 *     Uuid="{ProductID}"
 * />
 * 
 * <!-- Or use a blackboard variable for the Submodel ID -->
 * <MoveToPosition 
 *     Asset="{Xbot}"
 *     x="$aas{{HierarchySubmodelId}/EntryNode/{Station}/Location/x}"
 *     y="$aas{{HierarchySubmodelId}/EntryNode/{Station}/Location/y}"
 *     yaw="$aas{{HierarchySubmodelId}/EntryNode/{Station}/Location/theta}"
 *     Uuid="{ProductID}"
 * />
 * @endcode
 * 
 * Note: {Station} and {HierarchySubmodelId} in the path are substituted from 
 * the blackboard before AAS lookup.
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