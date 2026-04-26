#include "bt/bt_runtime_validator.h"

#include <algorithm>
#include <iostream>
#include <map>
#include <regex>
#include <set>
#include <sstream>
#include <unordered_set>

#include <behaviortree_cpp/behavior_tree.h>

#include "aas/aas_client.h"
#include "aas/aas_interface_cache.h"
#include "bt/conditions/fluent_check_node.h"
#include "bt/execution_refs.h"
#include "utils.h"

namespace bt_runtime_validator
{
    namespace
    {
        std::string lastSegmentLocal(const std::string &path)
        {
            auto pos = path.find_last_of('/');
            return pos == std::string::npos ? path : path.substr(pos + 1);
        }

        /// Resolve an interaction MQTT output topic for a given asset,
        /// preferring the cache and falling back to a live AAS query.
        bool hasOutputBinding(const std::string &asset_id,
                              const std::string &interaction,
                              AASInterfaceCache &cache,
                              AASClient &aas_client)
        {
            if (asset_id.empty() || interaction.empty())
                return false;
            if (cache.getInterface(asset_id, interaction, "output").has_value())
                return true;
            return aas_client.fetchInterface(asset_id, interaction, "output").has_value();
        }

        bool hasInputBinding(const std::string &asset_id,
                             const std::string &interaction,
                             AASInterfaceCache &cache,
                             AASClient &aas_client)
        {
            if (asset_id.empty() || interaction.empty())
                return false;
            if (cache.getInterface(asset_id, interaction, "input").has_value())
                return true;
            return aas_client.fetchInterface(asset_id, interaction, "input").has_value();
        }

        /// Issue a synchronous AAS GET to fetch the current value of a
        /// data-backed predicate so the corresponding FluentCheck node
        /// has something to evaluate on its very first tick.
        std::optional<nlohmann::json> seedPredicateValue(
            const bt_exec_refs::PredicateRef &ref,
            AASClient &aas_client)
        {
            if (ref.source_aas_id.empty() || ref.fluent_aas_path.empty())
                return std::nullopt;

            auto [submodel, remainder] = bt_exec_refs::splitSubmodelPath(ref.fluent_aas_path);
            if (submodel.empty())
            {
                submodel = "Variables";
                remainder = ref.fluent_aas_path;
            }
            try
            {
                return aas_client.fetchSubmodelElementByPath(
                    ref.source_aas_id, submodel, remainder);
            }
            catch (const std::exception &e)
            {
                std::cerr << "[bt_runtime_validator] AAS GET seed exception for "
                          << ref.source_aas_id << "/" << ref.fluent_aas_path
                          << ": " << e.what() << std::endl;
                return std::nullopt;
            }
        }

        void collectBlackboardKeyRefs(const BT::TreeNode *node,
                                      std::set<std::string> &referenced_keys)
        {
            if (!node)
                return;
            const auto &cfg = node->config();
            static const std::regex key_re(R"(\{([A-Za-z_][A-Za-z0-9_]*)\})");
            for (const auto &[port_name, raw_value] : cfg.input_ports)
            {
                auto begin = std::sregex_iterator(raw_value.begin(), raw_value.end(), key_re);
                auto end = std::sregex_iterator();
                for (auto it = begin; it != end; ++it)
                {
                    referenced_keys.insert((*it)[1].str());
                }
            }
            for (const auto &[port_name, raw_value] : cfg.output_ports)
            {
                auto begin = std::sregex_iterator(raw_value.begin(), raw_value.end(), key_re);
                auto end = std::sregex_iterator();
                for (auto it = begin; it != end; ++it)
                {
                    referenced_keys.insert((*it)[1].str());
                }
            }
        }

        /// Read a node's input-port value at *construction* time without
        /// going through ``getInput<>()``. BT.CPP's ``getInput<>`` port
        /// machinery dereferences ``{Key}`` references through the port
        /// remap layer, which is not always populated before the first
        /// tick. This helper instead reads the raw XML port string and,
        /// if it is a single ``{Key}`` reference, looks the key up
        /// directly via the node's own blackboard (preferred, honors
        /// ``_autoremap`` parent chains) and falls back to scanning all
        /// available blackboards.
        std::string resolvePortValue(const BT::TreeNode *node,
                                     const std::string &port_name,
                                     const std::vector<BT::Blackboard::Ptr> &blackboards)
        {
            if (!node)
                return std::string();
            const auto &cfg = node->config();
            auto it = cfg.input_ports.find(port_name);
            if (it == cfg.input_ports.end())
                return std::string();
            const std::string raw = it->second;
            if (raw.empty())
                return std::string();

            // Single ``{Key}`` reference -> direct blackboard lookup.
            static const std::regex single_key_re(R"(^\s*\{([A-Za-z_][A-Za-z0-9_]*)\}\s*$)");
            std::smatch m;
            if (std::regex_match(raw, m, single_key_re))
            {
                const std::string key = m[1].str();

                // Preferred: node's own blackboard. ``getAnyLocked`` walks
                // the parent chain set up by ``_autoremap`` so this picks
                // up MainTree's TreeNodesModel defaults from any nested
                // subtree.
                if (cfg.blackboard)
                {
                    try
                    {
                        if (auto any_locked = cfg.blackboard->getAnyLocked(key))
                        {
                            std::string out = any_locked.get()->cast<std::string>();
                            if (!out.empty())
                                return out;
                        }
                    }
                    catch (const std::exception &)
                    {
                        // Fall through to scan.
                    }
                }

                // Fallback: scan every known blackboard explicitly.
                for (const auto &bb : blackboards)
                {
                    if (!bb)
                        continue;
                    std::string out;
                    if (bb->get<std::string>(key, out) && !out.empty())
                        return out;
                }
                return std::string();
            }

            // Literal string (or templated value with multiple {Key}
            // references) -> return as-is. Validator only feeds the
            // result through JSON parsers that expect a complete payload,
            // so partial templates would have failed parsing anyway.
            return raw;
        }
    } // namespace

    ValidationResult validateAndSeed(BT::Tree &tree,
                                     AASInterfaceCache &cache,
                                     AASClient &aas_client)
    {
        ValidationResult result;
        if (!tree.rootNode())
        {
            NodeFailure f;
            f.reason = "Behavior tree has no root node";
            result.failures.push_back(f);
            return result;
        }

        std::set<std::string> referenced_bb_keys;

        // Build the list of blackboards once so we can resolve ``{Key}``
        // port references directly during the visitor walk (see
        // ``resolvePortValue``).
        std::vector<BT::Blackboard::Ptr> blackboards;
        if (auto root_bb = tree.rootBlackboard())
            blackboards.push_back(root_bb);
        for (const auto &sub : tree.subtrees)
        {
            if (sub && sub->blackboard)
                blackboards.push_back(sub->blackboard);
        }

        BT::applyRecursiveVisitor(
            tree.rootNode(),
            [&](BT::TreeNode *node)
            {
                if (!node)
                    return;

                collectBlackboardKeyRefs(node, referenced_bb_keys);

                const std::string &reg = node->registrationName();

                if (reg == "ExecuteAction")
                {
                    std::string ref_value = resolvePortValue(node, "action_ref", blackboards);
                    if (ref_value.empty())
                    {
                        NodeFailure f;
                        f.node_name = node->name();
                        f.registration_name = reg;
                        f.reason = "missing or empty action_ref input";
                        result.failures.push_back(f);
                        return;
                    }
                    auto parsed = bt_exec_refs::parseActionRef(ref_value);
                    if (!parsed.has_value())
                    {
                        NodeFailure f;
                        f.node_name = node->name();
                        f.registration_name = reg;
                        f.reason = "could not parse action_ref JSON payload";
                        result.failures.push_back(f);
                        return;
                    }
                    const std::string interaction = lastSegmentLocal(parsed->action_aas_path);
                    bool has_in = hasInputBinding(parsed->source_aas_id, interaction, cache, aas_client);
                    bool has_out = hasOutputBinding(parsed->source_aas_id, interaction, cache, aas_client);
                    if (!has_in || !has_out)
                    {
                        NodeFailure f;
                        f.node_name = node->name();
                        f.registration_name = reg;
                        f.source_aas_id = parsed->source_aas_id;
                        f.interaction = interaction;
                        std::ostringstream oss;
                        oss << "missing MQTT binding(s):";
                        if (!has_in)
                            oss << " input";
                        if (!has_out)
                            oss << " output";
                        f.reason = oss.str();
                        result.failures.push_back(f);
                    }
                    ++result.execute_actions_validated;
                }
                else if (reg == "FluentCheck")
                {
                    std::string ref_value = resolvePortValue(node, "predicate_ref", blackboards);
                    if (ref_value.empty())
                    {
                        NodeFailure f;
                        f.node_name = node->name();
                        f.registration_name = reg;
                        f.reason = "missing or empty predicate_ref input";
                        result.failures.push_back(f);
                        return;
                    }
                    auto parsed = bt_exec_refs::parsePredicateRef(ref_value);
                    if (!parsed.has_value())
                    {
                        NodeFailure f;
                        f.node_name = node->name();
                        f.registration_name = reg;
                        f.reason = "could not parse predicate_ref JSON payload";
                        result.failures.push_back(f);
                        return;
                    }
                    if (parsed->transformation_aas_path.empty())
                    {
                        // Symbolic-only predicate: no MQTT binding required.
                        ++result.fluent_checks_symbolic;
                        return;
                    }
                    const std::string interaction = lastSegmentLocal(parsed->fluent_aas_path);
                    bool has_out = hasOutputBinding(parsed->source_aas_id, interaction, cache, aas_client);
                    if (!has_out)
                    {
                        NodeFailure f;
                        f.node_name = node->name();
                        f.registration_name = reg;
                        f.source_aas_id = parsed->source_aas_id;
                        f.interaction = interaction;
                        f.reason = "missing MQTT output binding";
                        result.failures.push_back(f);
                        // Do not attempt to seed a node we cannot subscribe to.
                        return;
                    }
                    ++result.fluent_checks_validated;

                    // Seed initial value via synchronous AAS GET so the
                    // first tick has something to evaluate even before
                    // any MQTT publication arrives.
                    auto value_opt = seedPredicateValue(*parsed, aas_client);
                    if (value_opt.has_value())
                    {
                        if (auto *fc = dynamic_cast<FluentCheck *>(node))
                        {
                            fc->seedInitialValue(*value_opt);
                            ++result.fluent_checks_seeded;
                        }
                    }
                }
            });

        // Resolve every {Key} referenced from any port against the
        // tree's blackboards. The planner emits a ``PlannerRoot``
        // BehaviorTree whose only child is ``<SubTree ID="MainTree"/>``;
        // the alias-port and ``_planner_initial_state`` defaults are
        // declared on MainTree's TreeNodesModel SubTree entry, so they
        // land on the MainTree subtree blackboard, not the root one.
        // ``blackboards`` was already populated above for the visitor.
        for (const auto &key : referenced_bb_keys)
        {
            bool found = false;
            for (const auto &bb : blackboards)
            {
                if (bb->getEntry(key))
                {
                    found = true;
                    break;
                }
            }
            if (found)
                ++result.blackboard_refs_resolved;
            else
                result.unresolved_blackboard_keys.push_back(key);
        }
        return result;
    }

    std::string formatReport(const ValidationResult &result)
    {
        if (result.ok())
            return std::string();

        std::ostringstream oss;
        oss << "[bt_runtime_validator] startup validation FAILED:\n";
        if (!result.failures.empty())
        {
            // Group by source_aas_id for readability.
            std::map<std::string, std::vector<const NodeFailure *>> by_asset;
            for (const auto &f : result.failures)
            {
                by_asset[f.source_aas_id].push_back(&f);
            }
            oss << "  MQTT binding failures (" << result.failures.size() << "):\n";
            for (const auto &[asset, fs] : by_asset)
            {
                oss << "    asset='" << (asset.empty() ? std::string("<unknown>") : asset)
                    << "' (" << fs.size() << " node(s)):\n";
                for (const auto *f : fs)
                {
                    oss << "      - " << f->registration_name
                        << " name='" << f->node_name << "'"
                        << " interaction='" << f->interaction << "'"
                        << " :: " << f->reason << "\n";
                }
            }
        }
        if (!result.unresolved_blackboard_keys.empty())
        {
            oss << "  Unresolved blackboard keys ("
                << result.unresolved_blackboard_keys.size() << "):\n";
            for (const auto &k : result.unresolved_blackboard_keys)
            {
                oss << "      - {" << k << "}\n";
            }
        }
        return oss.str();
    }
} // namespace bt_runtime_validator
