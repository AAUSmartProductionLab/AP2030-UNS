#include "backends/mqtt/action_backend.h"

#include <jsonata/Jsonata.h>

#include "backends/aas/aas_client.h"
#include "backends/aas/aas_interface_cache.h"
#include "backends/aas/submodel_parsers/execution_model_parser.h"
#include "backends/backend_registry.h"
#include "backends/mqtt/mqtt_infra.h"
#include "bt/execution_refs.h"
#include "backends/mqtt/mqtt_client.h"
#include "backends/mqtt/node_message_distributor.h"
#include "utils.h"

#include <iostream>

namespace
{
    std::string lastSegment(const std::string &path)
    {
        if (path.empty())
            return path;
        std::string t = path;
        while (!t.empty() && (t.back() == '/' || t.back() == '.'))
            t.pop_back();
        auto p = t.find_last_of("/.");
        return (p == std::string::npos) ? t : t.substr(p + 1);
    }
}

// ── ResponseHandler ──────────────────────────────────────────────────

void MqttActionBackend::ResponseHandler::callback(
    const std::string &, const nlohmann::json &msg, mqtt::properties)
{
    std::lock_guard<std::mutex> lock(owner_.mutex_);
    if (msg.contains("Uuid") && msg["Uuid"].is_string() &&
        msg["Uuid"].get<std::string>() == owner_.current_uuid_)
    {
        owner_.last_response_ = msg;
        owner_.pending_terminal_ = BT::NodeStatus::SUCCESS;
    }
}

// ── MqttActionBackend ────────────────────────────────────────────────

MqttActionBackend::MqttActionBackend(IMqttClient &mqtt_client,
                                     AASClient &aas_client)
    : mqtt_client_(mqtt_client), aas_client_(aas_client)
{
    response_handler_ = std::make_unique<ResponseHandler>(mqtt_client, *this);
}

MqttActionBackend::~MqttActionBackend() = default;

void MqttActionBackend::initialize()
{
    // MQTT infrastructure (NMD, interface cache) is obtained from
    // BackendRegistry / MqttInfra at call sites.  No per-instance init needed.
}

BT::NodeStatus MqttActionBackend::onStart(const ActionContext &ctx)
{
    std::string asset_id = ctx.source_aas_id;
    if (!ctx.parameter_refs.empty() && !ctx.parameter_refs.front().aas_id.empty())
        asset_id = ctx.parameter_refs.front().aas_id;

    std::string interaction_name = lastSegment(ctx.action_aas_path);

    // Fetch JSONata expression from Skills ExecutionModel.
    std::unique_ptr<jsonata::Jsonata> jsonata_expr;
    {
        ExecutionModelParser emp(aas_client_);
        auto xform = emp.resolveTransformation(asset_id, interaction_name);
        if (xform.has_value() && !xform->empty())
        {
            try
            {
                jsonata_expr = std::make_unique<jsonata::Jsonata>(*xform);
            }
            catch (const std::exception &e)
            {
                std::cerr << "MqttActionBackend: JSONata compile error: " << e.what() << std::endl;
            }
        }
    }

    // Resolve MQTT topics via the shared SkillInterfaceCache.
    std::string input_topic, output_topic;
    auto *infra = BackendRegistry::instance().getMqttInfra();
    auto *cache = infra ? infra->getInterfaceCache() : nullptr;
    if (cache)
    {
        if (auto si = cache->resolve(asset_id, interaction_name))
        {
            if (si->has_input)
                input_topic = si->input_topic.getTopic();
            if (si->has_output)
                output_topic = si->output_topic.getTopic();
        }
    }
    if (input_topic.empty() || output_topic.empty())
    {
        std::cerr << "MqttActionBackend: missing topics for " << interaction_name << std::endl;
        return BT::NodeStatus::FAILURE;
    }

    // Build message via JSONata.
    current_uuid_ = mqtt_utils::generate_uuid();
    nlohmann::json message;
    if (jsonata_expr)
    {
        std::vector<bt_exec_refs::ParameterRef> param_refs;
        for (const auto &p : ctx.parameter_refs)
            param_refs.push_back({p.name, p.aas_id, p.aas_path});

        auto constants = aas_client_.fetchSiblingConstants(asset_id, "");
        auto params = aas_client_.fetchParamSnapshots(param_refs, true);

        nlohmann::json args_arr = nlohmann::json::array();
        for (const auto &t : ctx.args_tokens)
            args_arr.push_back(t);
        nlohmann::json params_arr = nlohmann::json::array();
        for (const auto &p : params)
            params_arr.push_back(p);

        auto c = nlohmann::json::object({{"args", args_arr}, {"params", params_arr}, {"constants", constants.is_null() ? nlohmann::json::object() : constants}, {"uuid", current_uuid_}});
        try
        {
            auto r = jsonata_expr->evaluate(nlohmann::ordered_json::parse(c.dump()));
            nlohmann::json rj = nlohmann::json::parse(nlohmann::json(r).dump());
            message = rj.is_object() ? std::move(rj) : nlohmann::json{{"value", rj}};
        }
        catch (const std::exception &e)
        {
            std::cerr << "MqttActionBackend: eval failed: " << e.what() << std::endl;
        }
    }
    if (!message.contains("Uuid"))
        message["Uuid"] = current_uuid_;
    else
        current_uuid_ = message["Uuid"].get<std::string>();

    // Register output handler + subscribe + publish.
    response_handler_->setTopic("output",
                                mqtt_utils::Topic(output_topic, nlohmann::json(), 1, false));
    if (infra)
        infra->getNmd()->registerDerivedInstance(response_handler_.get());

    mqtt_client_.subscribe_topic(output_topic, 1);
    mqtt_client_.publish_message(input_topic, message, 1);

    output_topic_ = output_topic;
    running_ = true;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        last_response_ = {};
        pending_terminal_.reset();
    }
    return BT::NodeStatus::RUNNING;
}

BT::NodeStatus MqttActionBackend::onRunning()
{
    std::lock_guard<std::mutex> lock(mutex_);
    if (pending_terminal_.has_value())
    {
        BT::NodeStatus s = *pending_terminal_;
        pending_terminal_.reset();
        return s;
    }
    return BT::NodeStatus::RUNNING;
}

void MqttActionBackend::onHalted()
{
    mqtt_client_.unsubscribe_topic(output_topic_);
    running_ = false;
}

nlohmann::json MqttActionBackend::responseData() const
{
    std::lock_guard<std::mutex> lock(mutex_);
    return last_response_;
}
