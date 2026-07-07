#pragma once

#include <behaviortree_cpp/bt_factory.h>
#include "backends/mqtt/mqtt_client.h"
#include "backends/aas/aas_client.h"
#include "utils.h"
#include "backends/mqtt/node_message_distributor.h"
#include "backends/backend_registry.h"
#include "backends/mqtt/mqtt_infra.h"
#include "bt/actions/execute_action_node.h"
#include "bt/conditions/fluent_check_node.h"

/// Register all BT node types.  Infrastructure (NMD, MQTT/AAS clients)
/// is obtained from BackendRegistry's MqttInfra — zero parameters needed
/// from the caller.
inline void registerAllNodes(BT::BehaviorTreeFactory &factory)
{
    // ── Planner-driven nodes (backend-driven, no protocol deps) ──────
    factory.registerBuilder<Skill>(
        "Skill",
        [](const std::string &name, const BT::NodeConfig &config)
        {
            auto node = std::make_unique<Skill>(name, config);
            node->initialize();
            return node;
        });

    factory.registerBuilder<Predicate>(
        "Predicate",
        [](const std::string &name, const BT::NodeConfig &config)
        {
            auto node = std::make_unique<Predicate>(name, config);
            node->initialize();
            return node;
        });
}
