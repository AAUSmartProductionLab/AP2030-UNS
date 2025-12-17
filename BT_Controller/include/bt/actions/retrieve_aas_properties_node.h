#pragma once

#include <behaviortree_cpp/action_node.h>
#include <behaviortree_cpp/bt_factory.h>
#include <nlohmann/json.hpp>
#include "aas/aas_client.h"
#include <string>

/**
 * @brief RetrieveAASPropertyNode retrieves a variable value from an Asset Administration Shell
 *
 * This node is similar to SetBlackboardNode but retrieves values from the AAS instead of
 * from a static value or input port. It directly queries the AAS for a property value
 * and writes it to the blackboard.
 *
 * Example usage in BT XML:
 * <RetrieveAASProperty Asset="FillingStation"
 *                      Submodel="TechnicalData"
 *                      Property="temperature"
 *                      output_key="station_temp"/>
 *
 * This will retrieve the "temperature" property from the "TechnicalData" submodel
 * of the "FillingStation" asset and write it to the blackboard key "station_temp".
 *
 * The Property port supports both simple property names and partial paths:
 * - Simple: Property="x" (finds first x property)
 * - Partial path: Property="Filling|Location|x" (finds x within Location within Filling)
 * Use pipe (|) as the path delimiter.
 */
class RetrieveAASPropertyNode : public BT::SyncActionNode
{
private:
    AASClient &aas_client_;

public:
    RetrieveAASPropertyNode(
        const std::string &name,
        const BT::NodeConfig &config,
        AASClient &aas_client)
        : BT::SyncActionNode(name, config), aas_client_(aas_client)
    {
        setRegistrationID("RetrieveAASProperty");
    }

    /**
     * @brief Defines the input and output ports for this node
     *
     * Input ports:
     * - Asset: The asset name to retrieve the property from
     * - Submodel: The submodel idShort containing the property
     * - Property: The property idShort or path to retrieve (use | as delimiter for paths)
     * - output_key: The blackboard key where the value should be written
     */
    static BT::PortsList providedPorts();

    /**
     * @brief Execute the node - retrieve value from AAS and write to blackboard
     *
     * This method:
     * 1. Gets Asset, Submodel, Property, and output_key from input ports
     * 2. Resolves asset name to asset ID
     * 3. Fetches the property value from the AAS
     * 4. Writes the value to the blackboard under output_key
     *
     * @return SUCCESS if value retrieved and written, FAILURE otherwise
     */
    virtual BT::NodeStatus tick() override;

    template <typename DerivedNode>
    static void registerNodeType(
        BT::BehaviorTreeFactory &factory,
        AASClient &aas_client,
        const std::string &node_name)
    {
        BT::NodeBuilder builder = [&aas_client](const std::string &name, const BT::NodeConfig &config)
        {
            return std::make_unique<DerivedNode>(name, config, aas_client);
        };

        BT::TreeNodeManifest manifest;
        manifest.type = BT::getType<DerivedNode>();
        manifest.ports = DerivedNode::providedPorts();
        manifest.registration_ID = node_name;
        factory.registerBuilder(manifest, builder);
    }
};
