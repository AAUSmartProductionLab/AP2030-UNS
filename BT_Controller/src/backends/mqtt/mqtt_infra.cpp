#include "backends/mqtt/mqtt_infra.h"
#include "backends/aas/submodel_parsers/mqtt_aid_protocol_parser.h"
#include "backends/mqtt/node_message_distributor.h"
#include "backends/mqtt/mqtt_client.h"
#include "backends/aas/aas_interface_cache.h"
#include "backends/aas/aas_client.h"

#include <mqtt/async_client.h>

MqttInfra::MqttInfra(const std::string &server_uri,
                     const std::string &client_id,
                     AASClient &aas_client)
    : aas_client_(aas_client)
{
    auto connOpts = mqtt::connect_options_builder::v5()
                        .clean_start(true)
                        .properties({{mqtt::property::SESSION_EXPIRY_INTERVAL, 604800}})
                        .finalize();

    mqtt_client_ = std::make_unique<PahoMqttClient>(server_uri, client_id, connOpts, 5);
    nmd_ = std::make_unique<NodeMessageDistributor>(*mqtt_client_);
    iface_cache_ = std::make_unique<SkillInterfaceCache>(aas_client.getAIDParser());
    mqtt_aid_parser_ = std::make_unique<MqttAidProtocolParser>();
    aas_client.registerProtocolParser(*mqtt_aid_parser_);
}

MqttInfra::~MqttInfra() = default;

void MqttInfra::initialize()
{
    setHandlerActive(true);
}

void MqttInfra::shutdown()
{
    setHandlerActive(false);
}

void MqttInfra::setHandlerActive(bool active)
{
    if (!mqtt_client_)
        return;

    if (active)
    {
        mqtt_client_->set_message_handler(
            [this](const std::string &topic, const nlohmann::json &payload,
                   mqtt::properties props)
            {
                nmd_->handle_incoming_message(topic, payload, props);
            });
    }
    else
    {
        mqtt_client_->set_message_handler({});
    }
}

void MqttInfra::suspendRouting()
{
    // Save the current handler so we can restore it exactly.
    // (In practice the handler is always the NMD-routing lambda, but
    //  we save/restore to be safe.)
    saved_handler_ = [this](const std::string &t, const nlohmann::json &p,
                            mqtt::properties pr)
    {
        nmd_->handle_incoming_message(t, p, pr);
    };
    mqtt_client_->set_message_handler({});
}

void MqttInfra::resumeRouting()
{
    if (saved_handler_)
        mqtt_client_->set_message_handler(saved_handler_);
    else
        setHandlerActive(true);
}

void MqttInfra::prepareForExecution(const BT::Tree &tree,
                                    std::chrono::milliseconds timeout)
{
    suspendRouting();
    nmd_->subscribeForActiveNodes(tree, timeout);
    resumeRouting();
}

void MqttInfra::unsubscribeTopics(const std::vector<std::string> &topics)
{
    if (!mqtt_client_)
        return;
    for (const auto &t : topics)
        mqtt_client_->unsubscribe_topic(t);
}
