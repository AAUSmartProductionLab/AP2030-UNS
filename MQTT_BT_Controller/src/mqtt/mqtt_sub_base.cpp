#include "mqtt/mqtt_sub_base.h"
#include "mqtt/node_message_distributor.h"
#include "mqtt/utils.h"
#include <iostream>

namespace fs = std::filesystem;
// Initialize the static member
NodeMessageDistributor *MqttSubBase::node_message_distributor_ = nullptr;

MqttSubBase::MqttSubBase(MqttClient &mqtt_client,
                         const std::string &response_topic = "",
                         const std::string &response_schema_path = "",
                         const int &subqos = 0)
    : mqtt_client_(mqtt_client),
      response_topic_(response_topic),
      response_topic_pattern_(response_topic),
      response_schema_path_(response_schema_path),
      response_schema_validator_(nullptr),
      subqos_(subqos)
{
    // Load schema if path is provided
    if (!response_schema_path_.empty())
    {
        response_schema_validator_ = mqtt_utils::createSchemaValidator(response_schema_path_);
    }
}

void MqttSubBase::processMessage(const json &msg, mqtt::properties props)
{
    if (response_schema_validator_)
    {
        try
        {
            response_schema_validator_->validate(msg);
        }
        catch (const std::exception &e)
        {
            std::cerr << "JSON validation failed: " << e.what() << std::endl;
            return;
        }
    }
    callback(msg, props);
}

bool MqttSubBase::isInterestedIn(const json &msg)
{
    std::cout << "Base isInterestedIn called - this should be overridden!" << std::endl;
    return false;
}

void MqttSubBase::setNodeMessageDistributor(NodeMessageDistributor *manager)
{
    node_message_distributor_ = manager;
}