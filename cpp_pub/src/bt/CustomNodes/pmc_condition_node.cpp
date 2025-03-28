#include "bt/CustomNodes/pmc_condition_node.h"
#include "mqtt/subscription_manager.h"
#include "common_constants.h"

PMCConditionNode::PMCConditionNode(const std::string &name, const BT::NodeConfig &config, Proxy &bt_proxy)
    : MqttValueComparisonCondition(name, config, bt_proxy,
                                   UNS_TOPIC,
                                   "../schemas/pmcCondition.schema.json")
{
    if (MqttValueComparisonCondition::subscription_manager_)
    {
        MqttValueComparisonCondition::subscription_manager_->registerDerivedInstance<PMCConditionNode>(this);
    }
}

BT::PortsList PMCConditionNode::providedPorts()
{
    return {
        BT::InputPort<std::string>("field_name", "Name of the field to monitor in the MQTT message"),
        BT::InputPort<std::string>("comparison_type", "Type of comparison: equal, not_equal, greater, less, contains"),
        BT::InputPort<std::string>("expected_value", "Value to compare against")};
}

bool PMCConditionNode::isInterestedIn(const std::string &field, const json &value)
{
    // Either call the parent implementation:
    return MqttValueComparisonCondition::isInterestedIn(field, value);

    // Or implement a custom version specific to PMC's requirements:
    // return field == field_name_ && [some additional PMC-specific condition];
}