#include "backends/mqtt/condition_backend.h"

#include <jsonata/Jsonata.h>

#include "backends/aas/aas_client.h"
#include "backends/aas/aas_interface_cache.h"
#include "backends/aas/transformation_resolver.h"
#include "bt/execution_refs.h"
#include "backends/mqtt/mqtt_client.h"
#include "backends/mqtt/node_message_distributor.h"
#include "utils.h"

#include <iostream>

// ── DataHandler (internal IMqttSubscriber) ───────────────────────────

MqttConditionBackend::DataHandler::DataHandler(
    IMqttClient &mqtt_client, MqttConditionBackend &owner)
    : IMqttSubscriber(mqtt_client), owner_(owner)
{
}

void MqttConditionBackend::DataHandler::callback(
    const std::string & /*topic_key*/,
    const nlohmann::json &msg,
    mqtt::properties /*props*/)
{
    owner_.latest_msg_ = msg;
}

// ── MqttConditionBackend ─────────────────────────────────────────────

MqttConditionBackend::MqttConditionBackend(
    IMqttClient &mqtt_client, AASClient &aas_client)
    : mqtt_client_(mqtt_client), aas_client_(aas_client)
{
    transformation_resolver_ = std::make_shared<TransformationResolver>(aas_client);
    data_handler_ = std::make_unique<DataHandler>(mqtt_client, *this);
}

MqttConditionBackend::~MqttConditionBackend() = default;

void MqttConditionBackend::initialize()
{
    // MQTT infrastructure obtained from BackendRegistry / MqttInfra.
}

bool MqttConditionBackend::isConfigured() const
{
    return topics_initialized_;
}

void MqttConditionBackend::seedInitialValue(const nlohmann::json &msg)
{
    latest_msg_ = msg;
}

bool MqttConditionBackend::initializeTopics()
{
    topics_initialized_ = true;
    return true;
}

std::optional<bool> MqttConditionBackend::evaluate(
    const std::string & /*predicate_name*/,
    const std::vector<std::string> & /*args*/)
{
    if (!jsonata_expr_)
        return std::nullopt;

    nlohmann::json params_array = nlohmann::json::array();
    for (const auto &p : param_snapshots_)
        params_array.push_back(p);

    nlohmann::json context = {
        {"data", latest_msg_.is_null() ? nlohmann::json::object() : latest_msg_},
        {"params", params_array},
        {"constants", constants_.is_null() ? nlohmann::json::object() : constants_},
    };

    try
    {
        auto result = jsonata_expr_->evaluate(
            nlohmann::ordered_json::parse(context.dump()));
        nlohmann::json rj = nlohmann::json::parse(nlohmann::json(result).dump());

        if (rj.is_boolean())
            return rj.get<bool>();
        if (rj.is_object() && rj.contains("value") && rj["value"].is_boolean())
            return rj["value"].get<bool>();

        return false;
    }
    catch (const std::exception &e)
    {
        std::cerr << "MqttConditionBackend: eval failed: " << e.what() << std::endl;
        return std::nullopt;
    }
}
