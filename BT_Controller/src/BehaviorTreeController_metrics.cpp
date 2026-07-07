/// Metrics collection, persistence, and registration config publishing.
/// Part of the BehaviorTreeController implementation split.

#include "BehaviorTreeController.h"

#include "bt/execution_refs.h"
#include "backends/backend_registry.h"
#include "backends/mqtt/mqtt_infra.h"
#include "utils.h"

#include <behaviortree_cpp/loggers/bt_observer.h>
#include <nlohmann/json.hpp>

#include <chrono>
#include <fstream>
#include <iostream>
#include <sstream>

// ── Local helpers ─────────────────────────────────────────────────────

namespace
{
    std::string classifyNodeCategory(const BT::TreeNode &node)
    {
        const std::string reg_name = node.registrationName();
        const BT::NodeType type = node.type();

        if (type == BT::NodeType::CONTROL)
        {
            if (reg_name.find("Selector") != std::string::npos ||
                reg_name.find("Fallback") != std::string::npos)
                return "selector";
            if (reg_name.find("Sequence") != std::string::npos)
                return "sequence";
            return "control_other";
        }
        if (type == BT::NodeType::ACTION)
            return "action";
        if (type == BT::NodeType::CONDITION)
            return "condition";
        if (type == BT::NodeType::DECORATOR)
            return "decorator";
        if (type == BT::NodeType::SUBTREE)
            return "subtree";
        return "leaf_other";
    }
} // namespace

// ── Metrics ───────────────────────────────────────────────────────────

void BehaviorTreeController::resetRunMetricsState()
{
    std::lock_guard<std::mutex> lock(metrics_mutex_);
    execute_timer_active_ = false;
    node_category_by_uid_.clear();
    bt_observer_.reset();
    current_run_id_.clear();
}

void BehaviorTreeController::initializeRunMetrics(const std::string &run_id)
{
    if (!bt_tree_.rootNode())
        return;

    std::string effective_run_id = run_id;
    if (effective_run_id.empty())
        effective_run_id = mqtt_utils::generate_uuid();

    std::lock_guard<std::mutex> lock(metrics_mutex_);
    current_run_id_ = effective_run_id;
    node_category_by_uid_.clear();
    bt_observer_ = std::make_unique<BT::TreeObserver>(bt_tree_);

    bt_tree_.applyVisitor(
        [this](const BT::TreeNode *node)
        {
            if (!node)
                return;
            node_category_by_uid_[node->UID()] = classifyNodeCategory(*node);
        });

    execute_started_at_ = std::chrono::steady_clock::now();
    execute_timer_active_ = true;
    std::cout << "Runtime metrics initialized for run_id=" << current_run_id_ << std::endl;
}

void BehaviorTreeController::publishRunMetrics(BT::NodeStatus final_status)
{
    nlohmann::json payload;
    std::string run_id;
    std::string process_id;
    {
        std::lock_guard<std::mutex> process_lock(process_aas_id_mutex_);
        process_id = process_aas_id_;
    }
    {
        std::lock_guard<std::mutex> lock(metrics_mutex_);
        if (!execute_timer_active_)
            return;

        run_id = current_run_id_;
        if (run_id.empty())
            run_id = mqtt_utils::generate_uuid();

        const auto elapsed =
            std::chrono::duration_cast<std::chrono::milliseconds>(
                std::chrono::steady_clock::now() - execute_started_at_)
                .count();

        payload["run_id"] = run_id;
        payload["controller_id"] = app_params_.clientId;
        payload["process_aas_id"] = process_id;
        payload["completed_at"] = bt_utils::getCurrentTimestampISO();
        payload["final_status"] = BT::toStr(final_status);
        payload["time_to_completion_s"] = static_cast<double>(elapsed) / 1000.0;

        nlohmann::json by_category = nlohmann::json::object();
        nlohmann::json by_node = nlohmann::json::array();

        unsigned total_transitions = 0;
        unsigned total_success = 0;
        unsigned total_failure = 0;
        unsigned total_skipped = 0;

        if (bt_observer_)
        {
            const auto &stats = bt_observer_->statistics();
            const auto &uid_to_path = bt_observer_->uidToPath();
            for (const auto &[uid, node_stats] : stats)
            {
                const auto category_it = node_category_by_uid_.find(uid);
                const std::string category =
                    category_it != node_category_by_uid_.end() ? category_it->second : "unknown";
                const auto path_it = uid_to_path.find(uid);
                const std::string path = path_it != uid_to_path.end() ? path_it->second : std::string();

                auto &bucket = by_category[category];
                if (!bucket.is_object())
                    bucket = nlohmann::json::object();

                bucket["transitions"] = bucket.value("transitions", 0u) + node_stats.transitions_count;
                bucket["success"] = bucket.value("success", 0u) + node_stats.success_count;
                bucket["failure"] = bucket.value("failure", 0u) + node_stats.failure_count;
                bucket["skipped"] = bucket.value("skipped", 0u) + node_stats.skip_count;

                total_transitions += node_stats.transitions_count;
                total_success += node_stats.success_count;
                total_failure += node_stats.failure_count;
                total_skipped += node_stats.skip_count;

                by_node.push_back({
                    {"uid", uid},
                    {"path", path},
                    {"category", category},
                    {"transitions", node_stats.transitions_count},
                    {"success", node_stats.success_count},
                    {"failure", node_stats.failure_count},
                    {"skipped", node_stats.skip_count},
                });
            }
        }

        payload["total_transitions"] = total_transitions;
        payload["total_success"] = total_success;
        payload["total_failure"] = total_failure;
        payload["total_skipped"] = total_skipped;
        payload["by_category"] = std::move(by_category);
        payload["by_node"] = std::move(by_node);

        execute_timer_active_ = false;
    }

    try
    {
        const std::string safe_run_id = sanitizeToken(run_id);
        std::filesystem::path output_dir = std::filesystem::path(app_params_.metrics_dir) / safe_run_id;
        std::filesystem::create_directories(output_dir);
        std::filesystem::path output_file = output_dir / "bt_controller.json";
        std::ofstream stream(output_file);
        if (stream.is_open())
        {
            stream << payload.dump(2);
            stream.close();
            std::cout << "Saved BT runtime metrics to " << output_file << std::endl;
        }
        else
        {
            std::cerr << "Failed to open metrics output file: " << output_file << std::endl;
        }
    }
    catch (const std::exception &e)
    {
        std::cerr << "Failed to persist BT runtime metrics: " << e.what() << std::endl;
    }

    // Metric output is via std::cout above and optionally persisted to
    // a file.  No MQTT publishing — run metrics are consumed from the
    // terminal / log output.
}

// ── Registration ──────────────────────────────────────────────────────

bool BehaviorTreeController::publishConfigToRegistrationService()
{
    if (app_params_.registration_config_path.empty() || app_params_.registration_topic.empty())
    {
        std::cout << "Registration not configured, skipping config publication" << std::endl;
        return true;
    }

    auto *mqtt = BackendRegistry::instance().getMqttInfra()
                     ? BackendRegistry::instance().getMqttInfra()->getMqttClient()
                     : nullptr;
    if (!mqtt || !mqtt->is_connected())
    {
        std::cerr << "Cannot publish registration config: message bus not connected" << std::endl;
        return false;
    }

    std::cout << "Loading AAS description config from: " << app_params_.registration_config_path << std::endl;

    std::ifstream config_file(app_params_.registration_config_path);
    if (!config_file.is_open())
    {
        std::cerr << "Failed to open AAS description config: " << app_params_.registration_config_path << std::endl;
        return false;
    }

    std::stringstream buffer;
    buffer << config_file.rdbuf();
    std::string yaml_content = buffer.str();
    config_file.close();

    if (yaml_content.empty())
    {
        std::cerr << "AAS description config file is empty: " << app_params_.registration_config_path << std::endl;
        return false;
    }

    std::cout << "Publishing registration config to: " << app_params_.registration_topic << std::endl;

    try
    {
        bool ok = mqtt->publish_message_raw(
            app_params_.registration_topic, yaml_content,
            2,    // QoS 2
            false // Don't retain
        );
        if (ok)
            std::cout << "Successfully published registration config to registration service" << std::endl;
        else
            std::cerr << "Failed to publish registration config" << std::endl;
        return ok;
    }
    catch (const std::exception &e)
    {
        std::cerr << "Failed to publish registration config: " << e.what() << std::endl;
        return false;
    }
}
