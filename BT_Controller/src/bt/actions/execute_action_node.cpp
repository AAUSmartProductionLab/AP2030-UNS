#include "bt/actions/execute_action_node.h"

#include <chrono>
#include <cstdlib>
#include <ctime>
#include <iostream>
#include <iomanip>
#include <mutex>
#include <sstream>

#include <jsonata/Jsonata.h>

#include "aas/aas_interface_cache.h"
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

std::string ExecuteAction::envFallbackMode()
{
    const char *raw = std::getenv("BT_CONTROLLER_AAS_DIRECT");
    if (!raw)
    {
        return "auto";
    }
    std::string s(raw);
    for (auto &c : s)
        c = static_cast<char>(::tolower(c));
    if (s == "force" || s == "disable" || s == "auto")
    {
        return s;
    }
    return "auto";
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

        // Try cached interface first, then live AAS query, then mark fallback.
        std::string fallback_mode = envFallbackMode();
        if (fallback_mode == "force")
        {
            aas_direct_fallback_ = true;
            topics_initialized_ = true;
            BT_LOG_INFO("ExecuteAction '" << this->name()
                << "' BT_CONTROLLER_AAS_DIRECT=force; using AAS-direct path");
            return;
        }

        const std::string &asset_id = action_ref_->source_aas_id;
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
            topics_initialized_ = true;
            return;
        }

        if (fallback_mode == "disable")
        {
            BT_LOG_ERROR("ExecuteAction '" << this->name()
                << "' missing interface and AAS-direct disabled by env");
            return;
        }

        // Mark for AAS-direct fallback. We do not require MQTT topics to be
        // set in this case; onStart will dispatch via AASClient::invokeOperation.
        aas_direct_fallback_ = true;
        topics_initialized_ = true;
        BT_LOG_INFO("ExecuteAction '" << this->name()
            << "' no Asset Interface Description; will use AAS-direct invoke for "
            << action_ref_->action_aas_path);
    }
    catch (const std::exception &e)
    {
        std::cerr << "ExecuteAction '" << this->name()
                  << "' initializeTopicsFromAAS exception: " << e.what() << std::endl;
    }
}

nlohmann::json ExecuteAction::createMessage()
{
    current_uuid_ = mqtt_utils::generate_uuid();
    nlohmann::json message;
    message["Uuid"] = current_uuid_;

    if (!action_ref_.has_value())
    {
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

    nlohmann::json context = {
        {"args", args_array},
        {"object_refs", object_refs_obj},
        {"now", nowIso8601()},
    };

    if (!jsonata_expr_)
    {
        std::cerr << "ExecuteAction '" << this->name()
                  << "' no JSONata expression compiled; sending bare uuid message" << std::endl;
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
            // Merge while preserving the Uuid we generated.
            for (auto it = result_json.begin(); it != result_json.end(); ++it)
            {
                message[it.key()] = it.value();
            }
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

    return message;
}

BT::NodeStatus ExecuteAction::onStart()
{
    // Lazy initialization mirrors the base class behavior.
    if (!topics_initialized_)
    {
        initializeTopicsFromAAS();
    }
    if (!action_ref_.has_value())
    {
        return BT::NodeStatus::FAILURE;
    }

    // Reset the per-tick effect-application latch so a re-entry of the
    // node (sequence retry, reactive replan) re-applies effects on its
    // next SUCCESS.
    effects_applied_ = false;

    if (!aas_direct_fallback_)
    {
        // Fast path: delegate to MqttActionNode lifecycle (publish input,
        // wait for output via callback).
        return MqttActionNode::onStart();
    }

    // AAS-direct fallback: synchronously invoke the operation and map the
    // response to BT success/failure. We still emit a Uuid for traceability.
    nlohmann::json input_message = createMessage();
    BT_LOG_DEBUG("ExecuteAction '" << this->name()
        << "' bound_args=" << nlohmann::json(args_tokens_).dump()
        << " action_aas_path=" << action_ref_->action_aas_path
        << " transformation=" << truncateForLog(transformation_expression_));

    try
    {
        // The planner emits action_aas_path with a leading submodel
        // segment ("AI-Planning/..."). Canonicalize it, then look up the
        // AIPlanning Action's SkillReference to find the actual Skills
        // operation to invoke. If resolution fails (e.g. older AAS without
        // SkillReference), fall back to invoking the path verbatim under
        // the Skills submodel.
        auto [planning_submodel, planning_remainder] =
            bt_exec_refs::splitSubmodelPath(action_ref_->action_aas_path);

        std::string invoke_submodel = "Skills";
        std::string invoke_path = action_ref_->action_aas_path;

        if (planning_submodel == "AIPlanning" && !planning_remainder.empty())
        {
            auto skill_ref = aas_client_.resolveSkillReference(
                action_ref_->source_aas_id, planning_remainder);
            if (skill_ref.has_value())
            {
                invoke_submodel = skill_ref->first;
                invoke_path = skill_ref->second;
            }
            else
            {
                std::cerr << "ExecuteAction '" << this->name()
                          << "' SkillReference unresolved; trying Skills/"
                          << planning_remainder << " verbatim" << std::endl;
                invoke_path = planning_remainder;
            }
        }

        auto response = aas_client_.invokeOperation(
            action_ref_->source_aas_id,
            invoke_submodel,
            invoke_path,
            input_message);
        if (!response.has_value())
        {
            std::cerr << "ExecuteAction '" << this->name()
                      << "' AAS invoke returned no response" << std::endl;
            return BT::NodeStatus::FAILURE;
        }
        if (response->is_object() && response->contains("error"))
        {
            std::cerr << "ExecuteAction '" << this->name()
                      << "' AAS invoke error: " << (*response)["error"].dump() << std::endl;
            return BT::NodeStatus::FAILURE;
        }
        applySymbolicEffects();
        return BT::NodeStatus::SUCCESS;
    }
    catch (const std::exception &e)
    {
        std::cerr << "ExecuteAction '" << this->name()
                  << "' AAS invoke exception: " << e.what() << std::endl;
        return BT::NodeStatus::FAILURE;
    }
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
    auto &state = SymbolicState::instance();
    for (const auto &atom : action_ref_->effects)
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
