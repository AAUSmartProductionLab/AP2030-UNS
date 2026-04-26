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

    /// Coerce an AAS Property's stringified ``value`` into the JSONata-friendly
    /// type implied by ``valueType``. AAS REST always serializes property
    /// values as strings; the planner transformations expect proper numbers
    /// and booleans (e.g. ``data.Position[0] - params[1].Parameters.Location.Position.X``
    /// needs both sides to be numbers).
    nlohmann::json coerceProperty(const nlohmann::json &elem)
    {
        if (!elem.contains("value"))
        {
            return nlohmann::json(nullptr);
        }
        const auto &raw = elem["value"];
        if (!raw.is_string())
        {
            return raw; // already typed
        }
        const std::string s = raw.get<std::string>();
        std::string vt = elem.value("valueType", "");
        try
        {
            if (vt == "xs:boolean")
            {
                return s == "true" || s == "1";
            }
            if (vt == "xs:integer" || vt == "xs:int" || vt == "xs:long" ||
                vt == "xs:short" || vt == "xs:byte" ||
                vt == "xs:nonNegativeInteger" || vt == "xs:positiveInteger" ||
                vt == "xs:unsignedInt" || vt == "xs:unsignedLong")
            {
                return std::stoll(s);
            }
            if (vt == "xs:double" || vt == "xs:float" || vt == "xs:decimal")
            {
                return std::stod(s);
            }
        }
        catch (const std::exception &)
        {
            // fall through to string
        }
        return s;
    }

    /// Recursively flatten an AAS submodel/SMC/Property/SubmodelElementList
    /// into idiomatic JSON: SMCs and Submodels become objects keyed by child
    /// idShort; SubmodelElementLists become arrays; Properties collapse to
    /// their typed value.
    nlohmann::json flattenAasElement(const nlohmann::json &elem)
    {
        if (!elem.is_object())
        {
            return elem;
        }
        const std::string mt = elem.value("modelType", "");
        if (mt == "Property")
        {
            return coerceProperty(elem);
        }
        if (mt == "SubmodelElementList")
        {
            nlohmann::json out = nlohmann::json::array();
            if (elem.contains("value") && elem["value"].is_array())
            {
                for (const auto &child : elem["value"])
                {
                    out.push_back(flattenAasElement(child));
                }
            }
            return out;
        }
        // Submodel root: children live under "submodelElements".
        if (elem.contains("submodelElements") && elem["submodelElements"].is_array())
        {
            nlohmann::json out = nlohmann::json::object();
            for (const auto &child : elem["submodelElements"])
            {
                if (child.is_object() && child.contains("idShort"))
                {
                    out[child["idShort"].get<std::string>()] = flattenAasElement(child);
                }
            }
            return out;
        }
        // SMC and other collection-shaped elements with a "value" array of
        // named children.
        if (elem.contains("value") && elem["value"].is_array())
        {
            nlohmann::json out = nlohmann::json::object();
            for (const auto &child : elem["value"])
            {
                if (child.is_object() && child.contains("idShort"))
                {
                    out[child["idShort"].get<std::string>()] = flattenAasElement(child);
                }
            }
            return out;
        }
        // Reference / unknown: return the raw value if any, else null.
        if (elem.contains("value"))
        {
            return elem["value"];
        }
        return nlohmann::json(nullptr);
    }

    /// Strip the trailing ``/Transformation`` (or any last segment) so the
    /// caller can address a sibling SMC like ``Constants``.
    std::string parentSlashPath(const std::string &slash_path)
    {
        if (slash_path.empty())
        {
            return slash_path;
        }
        auto pos = slash_path.find_last_of('/');
        if (pos == std::string::npos)
        {
            return std::string();
        }
        return slash_path.substr(0, pos);
    }

    /// Extract the value of the *last* Key in a ReferenceElement's
    /// ``value.keys`` array. Used to read a Variable's
    /// ``InterfaceReference`` and recover the interaction name (e.g.
    /// ``StationState`` / ``Location``) that lives under
    /// ``AssetInterfacesDescription``.
    std::optional<std::string> lastKeyValue(const nlohmann::json &reference_element)
    {
        if (!reference_element.is_object())
            return std::nullopt;
        if (!reference_element.contains("value") ||
            !reference_element["value"].is_object())
            return std::nullopt;
        const auto &val = reference_element["value"];
        if (!val.contains("keys") || !val["keys"].is_array() || val["keys"].empty())
            return std::nullopt;
        const auto &last = val["keys"].back();
        if (!last.contains("value") || !last["value"].is_string())
            return std::nullopt;
        return last["value"].get<std::string>();
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

            // Pre-fetch the Constants SMC sibling of this fluent's
            // Transformation (registration emits it from the YAML
            // ``constants:`` block). Optional: an empty object is fine.
            constants_ = nlohmann::json::object();
            const std::string parent_path = parentSlashPath(predicate_ref_->transformation_aas_path);
            if (!parent_path.empty())
            {
                auto constants_smc = aas_client_.fetchSubmodelElementByPath(
                    predicate_ref_->source_aas_id, "AIPlanning", parent_path + "/Constants");
                if (constants_smc.has_value())
                {
                    constants_ = flattenAasElement(*constants_smc);
                }
            }
        }

        // Pre-fetch each predicate parameter's AAS as a flattened JSON
        // snapshot so transformations can reference
        // ``params[i].Parameters.*`` / ``params[i].Variables.*`` without
        // per-tick HTTP round-trips. The ``Parameters`` half is static.
        // The ``Variables`` half is seeded from AAS defaults but is kept
        // *live* by per-Variable MQTT subscriptions registered below;
        // each Variable child carries an ``InterfaceReference`` reference
        // element naming the AssetInterfacesDescription property whose
        // MQTT topic this node should subscribe to. Failures to fetch a
        // submodel are tolerated -- the corresponding params[i] entry
        // stays an empty object so the transformation can still surface
        // a useful error.
        params_.clear();
        var_subscriptions_.clear();
        for (std::size_t i = 0; i < predicate_ref_->parameter_refs.size(); ++i)
        {
            const auto &p = predicate_ref_->parameter_refs[i];
            nlohmann::json snapshot = nlohmann::json::object();
            if (p.aas_id.empty())
            {
                params_.push_back(std::move(snapshot));
                continue;
            }

            // Static Parameters submodel.
            auto params_sm = aas_client_.fetchSubmodelElementByPath(
                p.aas_id, "Parameters", std::string());
            if (params_sm.has_value())
            {
                snapshot["Parameters"] = flattenAasElement(*params_sm);
            }

            // Variables submodel: keep the raw payload for InterfaceReference
            // discovery, then store the flattened version on the snapshot.
            auto vars_raw = aas_client_.fetchSubmodelElementByPath(
                p.aas_id, "Variables", std::string());
            if (vars_raw.has_value())
            {
                snapshot["Variables"] = flattenAasElement(*vars_raw);

                // Walk each Variable SMC, find its InterfaceReference, and
                // register an MQTT subscription whose callback will keep
                // params_[i]["Variables"][var_key] live.
                if (vars_raw->contains("submodelElements") &&
                    (*vars_raw)["submodelElements"].is_array())
                {
                    for (const auto &var_smc : (*vars_raw)["submodelElements"])
                    {
                        if (!var_smc.is_object() || !var_smc.contains("idShort"))
                            continue;
                        const std::string var_key =
                            var_smc["idShort"].get<std::string>();

                        // Locate the InterfaceReference child.
                        std::optional<std::string> interface_name;
                        if (var_smc.contains("value") && var_smc["value"].is_array())
                        {
                            for (const auto &child : var_smc["value"])
                            {
                                if (child.is_object() &&
                                    child.value("idShort", "") == "InterfaceReference")
                                {
                                    interface_name = lastKeyValue(child);
                                    break;
                                }
                            }
                        }
                        if (!interface_name.has_value() || interface_name->empty())
                            continue;

                        // Resolve the MQTT topic for this interface (output side).
                        std::optional<mqtt_utils::Topic> topic_opt;
                        auto cache = MqttSubBase::getAASInterfaceCache();
                        if (cache)
                        {
                            topic_opt = cache->getInterface(
                                p.aas_id, *interface_name, "output");
                        }
                        if (!topic_opt.has_value())
                        {
                            topic_opt = aas_client_.fetchInterface(
                                p.aas_id, *interface_name, "output");
                        }
                        if (!topic_opt.has_value())
                        {
                            std::cerr << "FluentCheck '" << this->name()
                                      << "' could not resolve MQTT output topic for "
                                      << "param[" << i << "].Variables." << var_key
                                      << " (interface=" << *interface_name
                                      << ", aas_id=" << p.aas_id << ")" << std::endl;
                            continue;
                        }

                        const std::string topic_key =
                            "p" + std::to_string(i) + ":" + var_key;
                        MqttSubBase::setTopic(topic_key, *topic_opt);
                        var_subscriptions_[topic_key] =
                            VarBinding{i, var_key};
                    }
                }
            }
            params_.push_back(std::move(snapshot));
        }

        // We are done. Even if no subscriptions were registered (e.g. a
        // fluent that depends only on static Parameters and Constants),
        // we mark initialization complete so tick() can evaluate
        // immediately against the static snapshot.
        topics_initialized_ = true;
    }
    catch (const std::exception &e)
    {
        std::cerr << "FluentCheck '" << this->name()
                  << "' initializeTopicsFromAAS exception: " << e.what() << std::endl;
    }
}

bool FluentCheck::evaluateAgainst()
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

    nlohmann::json params_array = nlohmann::json::array();
    {
        std::lock_guard<std::mutex> lock(mutex_);
        for (const auto &p : params_)
        {
            params_array.push_back(p);
        }
    }

    nlohmann::json context = {
        {"args", args_array},
        {"params", params_array},
        {"constants", constants_.is_null() ? nlohmann::json::object() : constants_},
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

    // Data-backed predicate: evaluate against the live params_ /
    // constants_ snapshot. ``evaluateAgainst`` snapshots the params under
    // mutex internally. The Variables slots were seeded from the AAS
    // submodel during initializeTopicsFromAAS and are kept current by
    // the per-Variable MQTT callbacks below.
    return evaluateAgainst() ? BT::NodeStatus::SUCCESS
                             : BT::NodeStatus::FAILURE;
}

void FluentCheck::callback(const std::string &topic_key,
                           const nlohmann::json &msg,
                           mqtt::properties /*props*/)
{
    auto it = var_subscriptions_.find(topic_key);
    if (it == var_subscriptions_.end())
    {
        return;
    }
    const auto &binding = it->second;

    std::lock_guard<std::mutex> lock(mutex_);
    if (binding.param_index >= params_.size())
    {
        return;
    }

    auto &param_entry = params_[binding.param_index];
    if (!param_entry.is_object())
    {
        param_entry = nlohmann::json::object();
    }
    if (!param_entry.contains("Variables") ||
        !param_entry["Variables"].is_object())
    {
        param_entry["Variables"] = nlohmann::json::object();
    }
    auto &slot = param_entry["Variables"][binding.var_key];

    // The slot was pre-populated by the AAS flatten with one Property
    // per declared Variable field. We update only those keys that exist
    // both in the slot and in the incoming message; this lets multiple
    // Variables share an MQTT topic but project disjoint fields (e.g.
    // PackMLState picks ``State`` while OccupationState picks
    // ``ProcessQueue`` from the same StationState message).
    if (msg.is_object() && slot.is_object())
    {
        for (auto it_slot = slot.begin(); it_slot != slot.end(); ++it_slot)
        {
            auto found = msg.find(it_slot.key());
            if (found != msg.end())
            {
                it_slot.value() = *found;
            }
        }
    }
    else if (msg.is_object())
    {
        // No declared field set (slot was non-object): copy whole message.
        slot = msg;
    }
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
