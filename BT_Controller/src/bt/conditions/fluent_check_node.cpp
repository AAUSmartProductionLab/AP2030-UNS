#include "bt/conditions/fluent_check_node.h"

#include <iostream>
#include <mutex>

#include <jsonata/Jsonata.h>

#include "aas/aas_interface_cache.h"
#include "bt/symbolic_state.h"
#include "mqtt/node_message_distributor.h"

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

    std::string truncateForLog(const std::string &text, size_t max_len = 200)
    {
        if (text.size() <= max_len)
        {
            return text;
        }
        return text.substr(0, max_len) + "...";
    }
}

std::shared_ptr<TransformationResolver> FluentCheck::getResolver(AASClient &aas_client)
{
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

FluentCheck::FluentCheck(const std::string &name,
                         const BT::NodeConfig &config,
                         MqttClient &mqtt_client,
                         AASClient &aas_client)
    : MqttSyncConditionNode(name, config, mqtt_client, aas_client)
{
}

FluentCheck::~FluentCheck() = default;

BT::PortsList FluentCheck::providedPorts()
{
    return {
        BT::InputPort<std::string>("predicate_ref"),
        BT::InputPort<std::string>("predicate_args"),
    };
}

void FluentCheck::initializeTopicsFromAAS()
{
    if (topics_initialized_)
    {
        return;
    }

    try
    {
        auto ref_input = getInput<std::string>("predicate_ref");
        if (!ref_input.has_value() || ref_input.value().empty())
        {
            std::cerr << "FluentCheck '" << this->name()
                      << "' missing predicate_ref input" << std::endl;
            return;
        }

        predicate_ref_ = bt_exec_refs::parsePredicateRef(ref_input.value());
        if (!predicate_ref_.has_value())
        {
            std::cerr << "FluentCheck '" << this->name()
                      << "' could not parse predicate_ref" << std::endl;
            return;
        }

        auto args_input = getInput<std::string>("predicate_args");
        args_tokens_ = args_input.has_value()
                           ? bt_exec_refs::parseArgsList(args_input.value())
                           : std::vector<std::string>{};

        interaction_name_ = lastSegment(predicate_ref_->fluent_aas_path);

        if (!predicate_ref_->transformation_aas_path.empty() &&
            !predicate_ref_->source_aas_id.empty())
        {
            auto resolver = getResolver(aas_client_);
            auto expr = resolver->getTransformationExpression(
                predicate_ref_->source_aas_id,
                predicate_ref_->transformation_aas_path);
            if (expr.has_value())
            {
                transformation_expression_ = *expr;
                try
                {
                    jsonata_expr_ = std::make_unique<jsonata::Jsonata>(transformation_expression_);
                }
                catch (const std::exception &e)
                {
                    std::cerr << "FluentCheck '" << this->name()
                              << "' JSONata compile error for "
                              << predicate_ref_->transformation_aas_path << ": "
                              << e.what() << std::endl;
                    jsonata_expr_.reset();
                }
            }
        }

        const std::string &asset_id = predicate_ref_->source_aas_id;
        bool subscriber_topic_set = false;

        auto cache = MqttSubBase::getAASInterfaceCache();
        if (cache && !asset_id.empty() && !interaction_name_.empty())
        {
            auto cached_output = cache->getInterface(asset_id, interaction_name_, "output");
            if (cached_output.has_value())
            {
                MqttSubBase::setTopic("output", cached_output.value());
                subscriber_topic_set = true;
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

        if (subscriber_topic_set)
        {
            topics_initialized_ = true;
            return;
        }

        // No interface description found - fall back to polling the AAS
        // Property value on each tick.
        aas_direct_fallback_ = true;
        topics_initialized_ = true;
        std::cout << "FluentCheck '" << this->name()
                  << "' no interface for " << interaction_name_
                  << "; will poll AAS property" << std::endl;
    }
    catch (const std::exception &e)
    {
        std::cerr << "FluentCheck '" << this->name()
                  << "' initializeTopicsFromAAS exception: " << e.what() << std::endl;
    }
}

bool FluentCheck::evaluateAgainst(const nlohmann::json &payload)
{
    if (!jsonata_expr_)
    {
        std::cerr << "FluentCheck '" << this->name()
                  << "' no JSONata expression compiled" << std::endl;
        return false;
    }

    nlohmann::json args_array = nlohmann::json::array();
    for (const auto &t : args_tokens_)
    {
        args_array.push_back(t);
    }

    nlohmann::json object_refs_obj = nlohmann::json::object();
    if (predicate_ref_.has_value())
    {
        for (const auto &p : predicate_ref_->parameter_refs)
        {
            if (p.name.empty())
                continue;
            object_refs_obj[p.name] = {
                {"aas_id", p.aas_id},
                {"aas_path", p.aas_path},
            };
        }
    }

    nlohmann::json context = {
        {"data", payload},
        {"args", args_array},
        {"object_refs", object_refs_obj},
    };

    try
    {
        auto data = nlohmann::ordered_json::parse(context.dump());
        auto result = jsonata_expr_->evaluate(data);
        nlohmann::json result_json = nlohmann::json::parse(
            nlohmann::json(result).dump());
        if (result_json.is_boolean())
        {
            return result_json.get<bool>();
        }
        if (result_json.is_object() && result_json.contains("value") &&
            result_json["value"].is_boolean())
        {
            return result_json["value"].get<bool>();
        }
        std::cerr << "FluentCheck '" << this->name()
                  << "' transformation returned non-boolean: "
                  << truncateForLog(result_json.dump()) << std::endl;
        return false;
    }
    catch (const std::exception &e)
    {
        std::cerr << "FluentCheck '" << this->name()
                  << "' evaluation failed (aas_id="
                  << (predicate_ref_.has_value() ? predicate_ref_->source_aas_id : "")
                  << ", path="
                  << (predicate_ref_.has_value() ? predicate_ref_->fluent_aas_path : "")
                  << ", expr=" << truncateForLog(transformation_expression_)
                  << "): " << e.what() << std::endl;
        return false;
    }
}

BT::NodeStatus FluentCheck::tick()
{
    if (!topics_initialized_)
    {
        initializeTopicsFromAAS();
    }
    if (!predicate_ref_.has_value())
    {
        return BT::NodeStatus::FAILURE;
    }

    // Symbolic-only predicates (StepReady / StepDone / etc.) carry an empty
    // transformation_aas_path. They are served from the process-wide
    // ``SymbolicState`` seeded from planner_metadata.initial_state and
    // mutated by ExecuteAction's symbolic effects.
    if (predicate_ref_->transformation_aas_path.empty())
    {
        return tickSymbolic();
    }

    nlohmann::json payload = nlohmann::json::object();

    if (aas_direct_fallback_)
    {
        try
        {
            // The fluent_aas_path is emitted by the planner with a
            // submodel-name prefix (typically "AI-Planning/..." which the
            // splitSubmodelPath helper canonicalizes to "AIPlanning/...").
            // Fall back to the Variables submodel when the prefix is unknown.
            auto [submodel, remainder] = bt_exec_refs::splitSubmodelPath(
                predicate_ref_->fluent_aas_path);
            if (submodel.empty())
            {
                submodel = "Variables";
                remainder = predicate_ref_->fluent_aas_path;
            }
            auto value_opt = aas_client_.fetchSubmodelElementByPath(
                predicate_ref_->source_aas_id, submodel, remainder);
            if (value_opt.has_value())
            {
                payload = *value_opt;
            }
            else
            {
                std::cerr << "FluentCheck '" << this->name()
                          << "' AAS-direct fetch returned no value" << std::endl;
                return BT::NodeStatus::FAILURE;
            }
        }
        catch (const std::exception &e)
        {
            std::cerr << "FluentCheck '" << this->name()
                      << "' AAS-direct fetch exception: " << e.what() << std::endl;
            return BT::NodeStatus::FAILURE;
        }
    }
    else
    {
        std::lock_guard<std::mutex> lock(mutex_);
        if (latest_msg_.is_null())
        {
            // No message yet: treat as not-yet-true rather than failure to
            // allow reactive control nodes to retry on the next tick.
            return BT::NodeStatus::FAILURE;
        }
        payload = latest_msg_;
    }

    return evaluateAgainst(payload) ? BT::NodeStatus::SUCCESS
                                    : BT::NodeStatus::FAILURE;
}

namespace
{
    /// Parse "predicate(arg1, arg2, ...)" out of the FluentCheck node's
    /// BT name. Returns ``std::nullopt`` when the node name does not match.
    std::optional<std::pair<std::string, std::vector<std::string>>>
    parseSymbolicNodeName(const std::string &name)
    {
        size_t open = name.find('(');
        if (open == std::string::npos || name.empty() || name.back() != ')')
        {
            return std::nullopt;
        }
        std::string predicate = name.substr(0, open);
        // Trim trailing whitespace from predicate.
        while (!predicate.empty() &&
               (predicate.back() == ' ' || predicate.back() == '\t'))
        {
            predicate.pop_back();
        }
        if (predicate.empty())
        {
            return std::nullopt;
        }

        std::string body = name.substr(open + 1, name.size() - open - 2);
        std::vector<std::string> args;
        std::string token;
        auto push = [&]()
        {
            size_t start = 0;
            size_t end = token.size();
            while (start < end && (token[start] == ' ' || token[start] == '\t'))
                ++start;
            while (end > start && (token[end - 1] == ' ' || token[end - 1] == '\t'))
                --end;
            if (start < end)
            {
                args.emplace_back(token.substr(start, end - start));
            }
            else if (!token.empty())
            {
                args.emplace_back();
            }
            token.clear();
        };
        for (char c : body)
        {
            if (c == ',')
            {
                push();
            }
            else
            {
                token.push_back(c);
            }
        }
        if (!token.empty() || !body.empty())
        {
            push();
        }
        return std::make_pair(predicate, args);
    }
}

BT::NodeStatus FluentCheck::tickSymbolic()
{
    auto parsed = parseSymbolicNodeName(this->name());
    if (!parsed.has_value())
    {
        std::cerr << "FluentCheck '" << this->name()
                  << "' symbolic predicate could not parse predicate(args) "
                     "from node name; returning FAILURE"
                  << std::endl;
        return BT::NodeStatus::FAILURE;
    }
    const auto &predicate = parsed->first;
    const auto &args = parsed->second;
    bool value = SymbolicState::instance().getBool(predicate, args);
    return value ? BT::NodeStatus::SUCCESS : BT::NodeStatus::FAILURE;
}
