#include "bt/actions/execute_action_node.h"

#include <chrono>
#include <ctime>
#include <iostream>
#include <iomanip>
#include <mutex>
#include <sstream>

#include <jsonata/Jsonata.h>

#include "aas/aas_interface_cache.h"
#include "aas/aas_snapshot.h"
#include "bt/bt_log.h"
#include "bt/symbolic_state.h"
#include "mqtt/node_message_distributor.h"
#include "utils.h"

namespace
{
    std::string lastSegment(const std::string &path)
    {
        if (path.empty())
        {
            return path;
        }
        std::string trimmed = path;
        while (!trimmed.empty() && (trimmed.back() == '/' || trimmed.back() == '.'))
        {
            trimmed.pop_back();
        }
        size_t slash = trimmed.find_last_of('/');
        size_t dot = trimmed.find_last_of('.');
        size_t pos = std::string::npos;
        if (slash != std::string::npos && dot != std::string::npos)
        {
            pos = std::max(slash, dot);
        }
        else if (slash != std::string::npos)
        {
            pos = slash;
        }
        else if (dot != std::string::npos)
        {
            pos = dot;
        }
        if (pos == std::string::npos)
        {
            return trimmed;
        }
        return trimmed.substr(pos + 1);
    }

    std::string nowIso8601()
    {
        auto now = std::chrono::system_clock::now();
        std::time_t t = std::chrono::system_clock::to_time_t(now);
        std::tm tm_buf{};
        gmtime_r(&t, &tm_buf);
        std::ostringstream oss;
        oss << std::put_time(&tm_buf, "%Y-%m-%dT%H:%M:%SZ");
        return oss.str();
    }

    std::string truncateForLog(const std::string &text, size_t max_len = 200)
    {
        if (text.size() <= max_len)
        {
            return text;
        }
        return text.substr(0, max_len) + "...";
    }
}

std::shared_ptr<TransformationResolver> ExecuteAction::getResolver(AASClient &aas_client)
{
    // Process-wide singleton keyed on the AASClient address; in practice
    // BT_Controller uses a single AASClient instance for its whole lifetime.
    static std::mutex mtx;
    static std::shared_ptr<TransformationResolver> instance;
    static AASClient *bound_client = nullptr;
    std::lock_guard<std::mutex> lock(mtx);
    if (!instance || bound_client != &aas_client)
    {
        instance = std::make_shared<TransformationResolver>(aas_client);
        bound_client = &aas_client;
    }
    return instance;
}

ExecuteAction::ExecuteAction(const std::string &name,
                             const BT::NodeConfig &config,
                             MqttClient &mqtt_client,
                             AASClient &aas_client)
    : MqttActionNode(name, config, mqtt_client, aas_client)
{
}

ExecuteAction::~ExecuteAction() = default;

BT::PortsList ExecuteAction::providedPorts()
{
    return {
        BT::InputPort<std::string>("action_ref"),
        BT::InputPort<std::string>("action_args"),
        BT::InputPort<std::string>("Uuid"),
    };
}

void ExecuteAction::initializeTopicsFromAAS()
{
    if (topics_initialized_)
    {
        return;
    }

    try
    {
        auto ref_input = getInput<std::string>("action_ref");
        if (!ref_input.has_value() || ref_input.value().empty())
        {
            std::cerr << "ExecuteAction '" << this->name()
                      << "' missing action_ref input" << std::endl;
            return;
        }

        action_ref_ = bt_exec_refs::parseActionRef(ref_input.value());
        if (!action_ref_.has_value())
        {
            std::cerr << "ExecuteAction '" << this->name()
                      << "' could not parse action_ref" << std::endl;
            return;
        }

        auto args_input = getInput<std::string>("action_args");
        args_tokens_ = args_input.has_value()
                           ? bt_exec_refs::parseArgsList(args_input.value())
                           : std::vector<std::string>{};

        interaction_name_ = lastSegment(action_ref_->action_aas_path);

        // Fetch the JSONata transformation expression once at construction.
        // Failure here does NOT abort initialization - the runtime will
        // still try direct invocation paths if a transformation is missing.
        if (!action_ref_->transformation_aas_path.empty() &&
            !action_ref_->source_aas_id.empty())
        {
            auto resolver = getResolver(aas_client_);
            auto expr = resolver->getTransformationExpression(
                action_ref_->source_aas_id,
                action_ref_->transformation_aas_path);
            if (expr.has_value())
            {
                transformation_expression_ = *expr;
                try
                {
                    jsonata_expr_ = std::make_unique<jsonata::Jsonata>(transformation_expression_);
                }
                catch (const std::exception &e)
                {
                    std::cerr << "ExecuteAction '" << this->name()
                              << "' JSONata compile error for "
                              << action_ref_->transformation_aas_path << ": "
                              << e.what() << std::endl;
                    jsonata_expr_.reset();
                }
            }
        }

        // Try cached interface first, then live AAS query. MQTT bindings
        // are required: the controller's startup validator aborts if any
        // ExecuteAction node lacks both input and output topics.
        //
        // Action merging in the planner deduplicates identical action
        // definitions across resources, keeping a single ``source_aas_id``.
        // For multi-instance resources (e.g. three planar shuttles sharing
        // the same Move action), that means ``source_aas_id`` no longer
        // identifies the executor. The first parameter (by convention the
        // TransportSystem / Resource) carries the actual instance AAS, so
        // we prefer its ``aas_id`` for MQTT topic resolution and fall back
        // to ``source_aas_id`` when no parameter is available.
        std::string asset_id = action_ref_->source_aas_id;
        if (!action_ref_->parameter_refs.empty() &&
            !action_ref_->parameter_refs.front().aas_id.empty())
        {
            asset_id = action_ref_->parameter_refs.front().aas_id;
        }
        bool publisher_topic_set = false;
        bool subscriber_topic_set = false;

        auto cache = MqttSubBase::getAASInterfaceCache();
        if (cache && !interaction_name_.empty() && !asset_id.empty())
        {
            auto cached_input = cache->getInterface(asset_id, interaction_name_, "input");
            auto cached_output = cache->getInterface(asset_id, interaction_name_, "output");
            if (cached_input.has_value())
            {
                MqttPubBase::setTopic("input", cached_input.value());
                publisher_topic_set = true;
            }
            if (cached_output.has_value())
            {
                MqttSubBase::setTopic("output", cached_output.value());
                subscriber_topic_set = true;
            }
        }

        if (!publisher_topic_set && !asset_id.empty() && !interaction_name_.empty())
        {
            auto request_opt = aas_client_.fetchInterface(asset_id, interaction_name_, "input");
            if (request_opt.has_value())
            {
                MqttPubBase::setTopic("input", request_opt.value());
                publisher_topic_set = true;
            }
        }
        if (!subscriber_topic_set && !asset_id.empty() && !interaction_name_.empty())
        {
            auto response_opt = aas_client_.fetchInterface(asset_id, interaction_name_, "output");
            if (response_opt.has_value())
            {
                MqttSubBase::setTopic("output", response_opt.value());
                subscriber_topic_set = true;
            }
        }

        if (publisher_topic_set && subscriber_topic_set)
        {
            // Pre-fetch the Constants SMC sibling of this action's
            // Transformation (registration emits it from the YAML
            // ``constants:`` block). Optional: an empty object is fine.
            constants_ = aas_snapshot::fetchSiblingConstants(
                aas_client_,
                action_ref_->source_aas_id,
                action_ref_->transformation_aas_path);

            // Pre-fetch each parameter's AAS as a flattened JSON snapshot
            // so the JSONata transformation can reference
            // ``params[i].Parameters.*`` / ``params[i].Variables.*``
            // without per-tick HTTP round-trips. Actions are one-shot
            // command builders, so we do NOT register live MQTT
            // subscriptions on Variables — the snapshot is captured at
            // initialization and reused for every onStart.
            params_ = aas_snapshot::fetchParamSnapshots(
                aas_client_,
                action_ref_->parameter_refs,
                /*include_variables=*/true);

            topics_initialized_ = true;
            return;
        }

        BT_LOG_ERROR("ExecuteAction '" << this->name()
                                       << "' missing MQTT interface for asset='" << asset_id
                                       << "' interaction='" << interaction_name_
                                       << "' (input_set=" << publisher_topic_set
                                       << ", output_set=" << subscriber_topic_set
                                       << "); startup validator will abort the run.");
        // Leave topics_initialized_ = false so the validator detects this node.
    }
    catch (const std::exception &e)
    {
        std::cerr << "ExecuteAction '" << this->name()
                  << "' initializeTopicsFromAAS exception: " << e.what() << std::endl;
    }
}

nlohmann::json ExecuteAction::createMessage()
{
    // Generate a fallback UUID up-front and expose it in the JSONata
    // context. The transformation may override the published ``Uuid``
    // field with a value pulled from a parameter (e.g. the Product's
    // Uuid for request/response correlation).
    const std::string fallback_uuid = mqtt_utils::generate_uuid();
    current_uuid_ = fallback_uuid;
    nlohmann::json message;

    if (!action_ref_.has_value())
    {
        message["Uuid"] = current_uuid_;
        return message;
    }

    // Build the JSONata evaluation context.
    nlohmann::json args_array = nlohmann::json::array();
    for (const auto &t : args_tokens_)
    {
        args_array.push_back(t);
    }

    nlohmann::json object_refs_obj = nlohmann::json::object();
    for (const auto &p : action_ref_->parameter_refs)
    {
        if (p.name.empty())
        {
            continue;
        }
        object_refs_obj[p.name] = {
            {"aas_id", p.aas_id},
            {"aas_path", p.aas_path},
        };
    }

    nlohmann::json params_array = nlohmann::json::array();
    for (const auto &p : params_)
    {
        params_array.push_back(p);
    }

    nlohmann::json context = {
        {"args", args_array},
        {"params", params_array},
        {"constants", constants_.is_null() ? nlohmann::json::object() : constants_},
        {"object_refs", object_refs_obj},
        {"now", nowIso8601()},
        {"uuid", fallback_uuid},
    };

    if (!jsonata_expr_)
    {
        BT_LOG_DEBUG("ExecuteAction '" << this->name()
                                       << "' no JSONata expression compiled; sending bare uuid message");
        message["Uuid"] = current_uuid_;
        return message;
    }

    try
    {
        auto data = nlohmann::ordered_json::parse(context.dump());
        auto result = jsonata_expr_->evaluate(data);
        nlohmann::json result_json = nlohmann::json::parse(
            nlohmann::json(result).dump());
        if (result_json.is_object())
        {
            // Adopt the transformation's full output verbatim. The
            // transformation owns the message shape, including ``Uuid``.
            message = std::move(result_json);
        }
        else
        {
            message["value"] = result_json;
        }
    }
    catch (const std::exception &e)
    {
        std::cerr << "ExecuteAction '" << this->name()
                  << "' JSONata eval failed (aas_id="
                  << action_ref_->source_aas_id << ", path="
                  << action_ref_->action_aas_path << ", expr="
                  << truncateForLog(transformation_expression_)
                  << "): " << e.what() << std::endl;
    }

    // Ensure the message carries a Uuid even if the transformation
    // omitted one. Actions correlate request/response by Uuid in
    // MqttActionNode::onMqttMessageReceived; current_uuid_ MUST match
    // whatever ends up published.
    if (!message.contains("Uuid") || !message["Uuid"].is_string() ||
        message["Uuid"].get<std::string>().empty())
    {
        message["Uuid"] = current_uuid_;
    }
    else
    {
        current_uuid_ = message["Uuid"].get<std::string>();
    }

    return message;
}

BT::NodeStatus ExecuteAction::onStart()
{
    // Lazy initialization AND late-init MQTT subscription registration.
    // Calling ensureInitialized() (instead of initializeTopicsFromAAS()
    // directly) is required so MqttActionNode registers this node with
    // the message distributor and subscribes to the response topic. Without
    // it the node publishes the command but never receives the response,
    // so the action stays RUNNING forever.
    if (!topics_initialized_)
    {
        ensureInitialized();
    }
    if (!action_ref_.has_value())
    {
        return BT::NodeStatus::FAILURE;
    }
    if (!topics_initialized_)
    {
        // Startup validator should have caught this; treat as hard failure.
        BT_LOG_ERROR("ExecuteAction '" << this->name()
                                       << "' onStart called without MQTT bindings; failing.");
        return BT::NodeStatus::FAILURE;
    }

    // Reset the per-tick effect-application latch so a re-entry of the
    // node (sequence retry, reactive replan) re-applies effects on its
    // next SUCCESS.
    effects_applied_ = false;

    // Build the outgoing message via the JSONata transformation,
    // validate it against the action's MQTT input schema, then publish.
    // We do NOT defer to MqttActionNode::onStart because we need to
    // intercept the message between createMessage() and publish() to
    // run the schema validator.
    nlohmann::json message = createMessage();

    auto it = MqttPubBase::topics_.find("input");
    if (it != MqttPubBase::topics_.end())
    {
        const auto &topic = it->second;
        // validateMessage returns false both for "failed validation" and
        // "no validator available". Distinguish by checking whether a
        // schema was provided.
        if (!topic.getSchema().is_null() && !topic.getSchema().empty())
        {
            if (!topic.validateMessage(message))
            {
                BT_LOG_ERROR("ExecuteAction '" << this->name()
                                               << "' produced a message that failed schema validation "
                                                  "against the action's input schema. Refusing to "
                                                  "publish. Message="
                                               << truncateForLog(message.dump())
                                               << " expr="
                                               << truncateForLog(transformation_expression_));
                return BT::NodeStatus::FAILURE;
            }
        }
    }

    publish("input", message);
    return BT::NodeStatus::RUNNING;
}

BT::NodeStatus ExecuteAction::onRunning()
{
    BT::NodeStatus s = MqttActionNode::onRunning();
    if (s == BT::NodeStatus::SUCCESS)
    {
        applySymbolicEffects();
    }
    return s;
}

void ExecuteAction::applySymbolicEffects()
{
    if (effects_applied_ || !action_ref_.has_value())
    {
        return;
    }
    effects_applied_ = true;
    if (action_ref_->effects.empty())
    {
        return;
    }

    // Read the FOND outcome discriminator from the latest response
    // payload. The simulator/station is expected to publish an integer
    // ``Outcome`` field on SUCCESS for FOND actions; legacy stations
    // (and all non-FOND actions) omit it, in which case branch 0 — the
    // declaration-order first oneOf child, or the lone deterministic
    // branch for non-FOND actions — is selected.
    int outcome = 0;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        if (last_response_msg_.is_object()
            && last_response_msg_.contains("Outcome")
            && last_response_msg_["Outcome"].is_number_integer())
        {
            outcome = last_response_msg_["Outcome"].get<int>();
        }
    }

    const bt_exec_refs::EffectBranch *selected = nullptr;
    for (const auto &branch : action_ref_->effects)
    {
        if (branch.index == outcome)
        {
            selected = &branch;
            break;
        }
    }
    if (selected == nullptr)
    {
        BT_LOG_ERROR("ExecuteAction '" << this->name()
                                       << "' received Outcome=" << outcome
                                       << " but no matching effect branch was emitted by "
                                          "the planner; falling back to branch 0.");
        selected = &action_ref_->effects.front();
    }

    BT_LOG_DEBUG("ExecuteAction '" << this->name()
                                   << "' applying FOND outcome branch " << selected->index
                                   << " (" << selected->atoms.size() << " atoms)");

    auto &state = SymbolicState::instance();
    for (const auto &atom : selected->atoms)
    {
        if (atom.predicate.empty())
        {
            continue;
        }
        // Boolean false / explicit erase semantics: drop the key so a
        // missing-key lookup also reads as false.
        if (atom.value.is_boolean() && atom.value.get<bool>() == false)
        {
            state.erase(atom.predicate, atom.args);
        }
        else
        {
            state.set(atom.predicate, atom.args, atom.value);
        }
        BT_LOG_DEBUG("ExecuteAction '" << this->name()
                                       << "' applied symbolic effect "
                                       << SymbolicState::canonicalKey(atom.predicate, atom.args)
                                       << " = " << atom.value.dump());
    }
}
