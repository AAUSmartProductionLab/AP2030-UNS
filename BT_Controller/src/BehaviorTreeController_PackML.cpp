/// PackML state machine — ISA-88 compliant control loop, state actions,
/// BT initialization pipeline, and API callbacks.
///
/// Command  → Transition
///  Start   → IDLE → STARTING → EXECUTE
///  Stop    → any  → STOPPING → STOPPED
///  Reset   → STOPPED/COMPLETE/ABORTED → RESETTING → IDLE
///  Abort   → any  → ABORTING → ABORTED  (SIGINT maps here)
///  Clear   → ABORTED/STOPPED → CLEARING → STOPPED

#include "BehaviorTreeController.h"

#include "bt/execution_refs.h"
#include "bt/bt_runtime_validator.h"
#include "bt/register_all_nodes.h"
#include "backends/backend_registry.h"
#include "utils.h"

#include <behaviortree_cpp/loggers/groot2_publisher.h>
#include <behaviortree_cpp/xml_parsing.h>

#include <iostream>
#include <fstream>
#include <sstream>
#include <mutex>
#include <thread>
#include <chrono>

// ═══════════════════════════════════════════════════════════════════════
// Main PackML control loop
// ═══════════════════════════════════════════════════════════════════════

int BehaviorTreeController::run()
{
    if (handleGenerateXmlModelsOption())
        return 0;

    while (true)
    {
        // ── Command dispatch ─────────────────────────────────────
        if (abort_command_.load())
        {
            Aborting();
            abort_command_ = false;
            break;
        }
        else if (clear_command_.load() &&
                 (current_packml_state_ == PackML::State::ABORTED))
        {
            Clearing();
            clear_command_ = false;
        }
        else if (stop_command_.load())
        {
            Stopping();
            stop_command_ = false;
        }
        else if (reset_command_.load() &&
                 (current_packml_state_ == PackML::State::STOPPED ||
                  current_packml_state_ == PackML::State::COMPLETE))
        {
            Resetting();
            reset_command_ = false;
        }
        else if (start_command_.load() &&
                 current_packml_state_ == PackML::State::IDLE)
        {
            Starting();
            start_command_ = false;
        }
        else if (hold_command_.load() &&
                 current_packml_state_ == PackML::State::EXECUTE)
        {
            Holding();
            hold_command_ = false;
        }
        else if (unhold_command_.load() &&
                 current_packml_state_ == PackML::State::HELD)
        {
            Unholding();
            unhold_command_ = false;
        }
        else if (suspend_command_.load() &&
                 current_packml_state_ == PackML::State::EXECUTE)
        {
            Suspending();
            suspend_command_ = false;
        }
        else if (unsuspend_command_.load() &&
                 current_packml_state_ == PackML::State::SUSPENDED)
        {
            Unsuspending();
            unsuspend_command_ = false;
        }

        // ── State actions ────────────────────────────────────────
        if (current_packml_state_ == PackML::State::EXECUTE)
            Execute();
        else if (current_packml_state_ == PackML::State::COMPLETE ||
                 current_packml_state_ == PackML::State::HELD ||
                 current_packml_state_ == PackML::State::SUSPENDED)
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
        else
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }
    return 0;
}

// ═══════════════════════════════════════════════════════════════════════
// PackML state actions
// ═══════════════════════════════════════════════════════════════════════

void BehaviorTreeController::Abort()
{
    abort_command_ = true;
}

void BehaviorTreeController::Clear()
{
    clear_command_ = true;
}

void BehaviorTreeController::Stop()
{
    stop_command_ = true;
}

void BehaviorTreeController::Reset()
{
    reset_command_ = true;
}

void BehaviorTreeController::Start(const std::string &process_id)
{
    {
        std::lock_guard<std::mutex> lk(process_aas_id_mutex_);
        process_aas_id_ = process_id;
    }
    start_command_ = true;
}

bool BehaviorTreeController::isRunning() const
{
    return current_packml_state_ == PackML::State::EXECUTE;
}

void BehaviorTreeController::Hold()
{
    hold_command_ = true;
}

void BehaviorTreeController::Unhold()
{
    unhold_command_ = true;
}

void BehaviorTreeController::Suspend()
{
    suspend_command_ = true;
}

void BehaviorTreeController::Unsuspend()
{
    unsuspend_command_ = true;
}

void BehaviorTreeController::Starting()
{
    std::cout << "====== Starting ======" << std::endl;
    current_packml_state_ = PackML::State::STARTING;

    std::string pid;
    {
        std::lock_guard<std::mutex> lk(process_aas_id_mutex_);
        pid = process_aas_id_;
    }
    if (pid.empty())
    {
        Aborting();
        return;
    }

    stop_command_ = reset_command_ = abort_command_ = false;

    if (!setupEquipmentAndNodes(pid))
    {
        Aborting();
        return;
    }
    if (!createBehaviorTree(pid))
    {
        Aborting();
        return;
    }
    if (!validateAndFinalizeTree())
    {
        Aborting();
        return;
    }

    bt_publisher_ = std::make_unique<BT::Groot2Publisher>(bt_tree_, app_params_.groot2_port);
    {
        std::lock_guard<std::mutex> lk(metrics_mutex_);
        initializeRunMetrics(current_run_id_);
    }

    current_packml_state_ = PackML::State::EXECUTE;
    current_bt_tick_status_ = BT::NodeStatus::IDLE;
    std::cout << "State: " << PackML::stateToString(PackML::State::EXECUTE) << std::endl;
}

void BehaviorTreeController::Execute()
{
    if (!bt_tree_.rootNode())
    {
        current_packml_state_ = PackML::State::IDLE;
        return;
    }

    BT::NodeStatus r = bt_tree_.tickOnce();
    bt_tree_.sleep(std::chrono::milliseconds(100));

    if (BT::isStatusCompleted(r))
    {
        Completing();
        current_bt_tick_status_ = r;
        current_packml_state_ = PackML::State::COMPLETE;
        std::cout << "State: " << PackML::stateToString(PackML::State::COMPLETE) << std::endl;
    }
    else
    {
        current_bt_tick_status_ = r;
    }
}

void BehaviorTreeController::Completing()
{
    std::cout << "BT completed: " << BT::toStr(current_bt_tick_status_) << std::endl;
    publishRunMetrics(current_bt_tick_status_);
}

void BehaviorTreeController::Complete()
{
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
}

void BehaviorTreeController::Resetting()
{
    std::cout << "====== Resetting ======" << std::endl;
    current_packml_state_ = PackML::State::RESETTING;

    start_command_ = reset_command_ = stop_command_ = abort_command_ = false;
    {
        std::lock_guard<std::mutex> lk(process_aas_id_mutex_);
        process_aas_id_.clear();
    }

    BackendRegistry::instance().deinitializeAll();

    if (bt_tree_.rootNode())
    {
        bt_tree_.haltTree();
        bt_publisher_.reset();
    }
    resetRunMetricsState();

    bt_tree_ = BT::Tree();
    bt_factory_ = std::make_unique<BT::BehaviorTreeFactory>();
    nodes_registered_ = false;

    current_packml_state_ = PackML::State::IDLE;
    std::cout << "State: " << PackML::stateToString(PackML::State::IDLE) << std::endl;
}

void BehaviorTreeController::Stopping()
{
    current_packml_state_ = PackML::State::STOPPING;
    if (bt_tree_.rootNode())
        bt_tree_.haltTree();
    current_packml_state_ = PackML::State::STOPPED;
    std::cout << "State: " << PackML::stateToString(PackML::State::STOPPED) << std::endl;
}

void BehaviorTreeController::Aborting()
{
    current_packml_state_ = PackML::State::ABORTING;
    if (bt_tree_.rootNode())
        bt_tree_.haltTree();
    current_packml_state_ = PackML::State::ABORTED;
    std::cout << "State: " << PackML::stateToString(PackML::State::ABORTED) << std::endl;
}

void BehaviorTreeController::Clearing()
{
    std::cout << "====== Clearing ======" << std::endl;
    current_packml_state_ = PackML::State::CLEARING;
    start_command_ = reset_command_ = stop_command_ = abort_command_ = false;
    {
        std::lock_guard<std::mutex> lk(process_aas_id_mutex_);
        process_aas_id_.clear();
    }
    current_packml_state_ = PackML::State::STOPPED;
    std::cout << "State: " << PackML::stateToString(PackML::State::STOPPED) << std::endl;
}

void BehaviorTreeController::Holding()
{
    std::cout << "====== Holding ======" << std::endl;
    current_packml_state_ = PackML::State::HOLDING;
    if (bt_tree_.rootNode())
        bt_tree_.haltTree();
    current_packml_state_ = PackML::State::HELD;
    std::cout << "State: " << PackML::stateToString(PackML::State::HELD) << std::endl;
}

void BehaviorTreeController::Unholding()
{
    std::cout << "====== Unholding ======" << std::endl;
    current_packml_state_ = PackML::State::UNHOLDING;
    // Tree was halted by Hold — caller must re-start via Starting().
    // For now, recover to EXECUTE to resume ticking.
    current_packml_state_ = PackML::State::EXECUTE;
    current_bt_tick_status_ = BT::NodeStatus::IDLE;
    std::cout << "State: " << PackML::stateToString(PackML::State::EXECUTE) << std::endl;
}

void BehaviorTreeController::Suspending()
{
    std::cout << "====== Suspending ======" << std::endl;
    current_packml_state_ = PackML::State::SUSPENDING;
    if (bt_tree_.rootNode())
        bt_tree_.haltTree();
    current_packml_state_ = PackML::State::SUSPENDED;
    std::cout << "State: " << PackML::stateToString(PackML::State::SUSPENDED) << std::endl;
}

void BehaviorTreeController::Unsuspending()
{
    std::cout << "====== Unsuspending ======" << std::endl;
    current_packml_state_ = PackML::State::UNSUSPENDING;
    current_packml_state_ = PackML::State::EXECUTE;
    current_bt_tick_status_ = BT::NodeStatus::IDLE;
    std::cout << "State: " << PackML::stateToString(PackML::State::EXECUTE) << std::endl;
}
