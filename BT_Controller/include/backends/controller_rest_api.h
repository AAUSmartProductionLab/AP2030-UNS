#pragma once

#include <string>
#include <thread>
#include <atomic>

class BehaviorTreeController;

/// Minimal REST API for the BT_Controller, following the same pattern
/// as Registration_Service's operation delegation API but in-process.
///
/// Exposes controller functions as HTTP endpoints so they can be
/// invoked as AAS Operations via invocationDelegation.
///
/// Endpoints:
///   POST /operations/Start     {"Process": "<aas_id>"}  → IDLE → STARTING
///   POST /operations/Stop      {}                        → any → STOPPING
///   POST /operations/Reset     {}                        → STOPPED/COMPLETE/ABORTED → RESETTING
///   POST /operations/Abort     {}                        → any → ABORTING
///   POST /operations/Clear     {}                        → ABORTED/STOPPED → CLEARING
///   POST /operations/Hold      {}                        → EXECUTE → HOLDING → HELD
///   POST /operations/Unhold    {}                        → HELD → UNHOLDING → EXECUTE
///   POST /operations/Suspend   {}                        → EXECUTE → SUSPENDING → SUSPENDED
///   POST /operations/Unsuspend {}                        → SUSPENDED → UNSUSPENDING → EXECUTE
///   GET  /health                                        → status
class ControllerRestApi
{
public:
    ControllerRestApi(int port, BehaviorTreeController *controller);
    ~ControllerRestApi();

    /// Start the HTTP server in a background thread.
    void start();

    /// Stop the server.
    void stop();

    /// The port the server is listening on.
    int port() const { return port_; }

private:
    int port_;
    BehaviorTreeController *controller_;
    std::thread thread_;
    std::atomic<bool> running_{false};
};
