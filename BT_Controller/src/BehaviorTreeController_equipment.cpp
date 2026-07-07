/// Node lifecycle: registration, unregistration,
/// interface pre-fetch, topic subscription, and BT initialization pipeline.
/// Part of the BehaviorTreeController implementation split.

#include "BehaviorTreeController.h"

#include <behaviortree_cpp/loggers/groot2_publisher.h>
#include <behaviortree_cpp/xml_parsing.h>

#include "bt/register_all_nodes.h"
#include "bt/execution_refs.h"
#include "bt/bt_runtime_validator.h"
#include "backends/backend_registry.h"
#include "utils.h"

#include <iostream>
#include <fstream>
#include <sstream>
#include <chrono>

// ── Node registration ─────────────────────────────────────────────────

bool BehaviorTreeController::registerNodesWithAASConfig()
{
    try
    {
        registerAllNodes(*bt_factory_);

        // Backend-polymorphic initialization — MQTT backends set up
        // NMD / interface cache; AAS / KG backends are no-ops.
        BackendRegistry::instance().initializeAll();
        return true;
    }
    catch (const std::exception &e)
    {
        std::cerr << "Exception during node registration: " << e.what() << std::endl;
        return false;
    }
}

void BehaviorTreeController::unregisterAllNodes()
{
    if (bt_tree_.rootNode())
        bt_tree_.haltTree();
    bt_publisher_.reset();

    // Generic de-init: unsubscribe topics, clear backend + interface caches.
    BackendRegistry::instance().deinitializeAll();

    // Full teardown: shut down backends + MQTT transport statics.
    BackendRegistry::instance().shutdownAll();

    bt_factory_ = std::make_unique<BT::BehaviorTreeFactory>();
    nodes_registered_ = false;
    std::cout << "All nodes unregistered." << std::endl;
}

// ── Interface pre-fetch / topic subscription (MQTT backend only) ──────

bool BehaviorTreeController::prefetchAssetInterfaces()
{
    // Interfaces are now lazily resolved per-skill by SkillInterfaceCache
    // via resolveSkillInterface().  No bulk pre-fetch needed.
    return true;
}

// ═══════════════════════════════════════════════════════════════════════
// BT initialization pipeline
// ═══════════════════════════════════════════════════════════════════════

bool BehaviorTreeController::setupEquipmentAndNodes(const std::string &)
{
    // prefetchAssetInterfaces(); // removed: interfaces are now lazily resolved per-skill
    if (!registerNodesWithAASConfig())
    {
        nodes_registered_ = false;
        return false;
    }
    nodes_registered_ = true;
    return true;
}

bool BehaviorTreeController::createBehaviorTree(const std::string &pid)
{
    try
    {
        auto u = BackendRegistry::instance().getAasClient()->fetchPolicyBTUrl(pid);
        if (!u.has_value())
            return false;
        std::string url = u.value();

        std::string xml;
        {
            const std::string &dir = app_params_.bt_local_descriptions_dir;
            const std::string &gp = app_params_.bt_description_base_url;
            if (!dir.empty() && url.rfind(gp, 0) == 0)
            {
                std::string fn = url.substr(gp.size());
                std::ifstream fs(dir + "/" + fn);
                if (fs.is_open())
                {
                    std::stringstream ss;
                    ss << fs.rdbuf();
                    xml = ss.str();
                }
            }
        }
        if (xml.empty())
            xml = schema_utils::fetchContentFromUrl(url);
        if (xml.empty())
            return false;

        auto bb = BT::Blackboard::create();
        bb->set("ProcessAASId", pid);

        // With inlined refs, BT.CPP handles all port values directly —
        // no TreeNodesModel defaults need manual application.
        bt_tree_ = bt_factory_->createTreeFromText(xml, bb);

        return true;
    }
    catch (const BT::RuntimeError &e)
    {
        return false;
    }
}

bool BehaviorTreeController::validateAndFinalizeTree()
{
    BackendRegistry::instance().prepareForExecution(bt_tree_);

    if (auto *cache = BackendRegistry::instance().getInterfaceCache())
    {
        auto v = bt_runtime_validator::validateAndSeed(bt_tree_, *cache);
        if (!v.ok())
        {
            std::cerr << bt_runtime_validator::formatReport(v) << std::endl;
            if (bt_tree_.rootNode())
                bt_tree_.haltTree();
            bt_publisher_.reset();
            return false;
        }
    }
    return true;
}
