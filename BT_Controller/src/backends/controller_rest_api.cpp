#include "backends/controller_rest_api.h"
#include "BehaviorTreeController.h"

#define CPPHTTPLIB_OPENSSL_SUPPORT 0
#include "httplib.h"

#include <nlohmann/json.hpp>

#include <iostream>

using namespace httplib;

ControllerRestApi::ControllerRestApi(int port, BehaviorTreeController *controller)
    : port_(port), controller_(controller)
{
    start();
}

ControllerRestApi::~ControllerRestApi()
{
    stop();
}

void ControllerRestApi::start()
{
    if (running_)
        return;
    running_ = true;

    thread_ = std::thread([this]()
                          {
        Server svr;

        svr.Post("/operations/Start", [this](const Request &req, Response &res)
        {
            std::string process_id;
            if (req.has_param("Process"))
                process_id = req.get_param_value("Process");
            else if (auto body = nlohmann::json::parse(req.body, nullptr, false);
                     !body.is_null() && body.contains("Process"))
                process_id = body["Process"].get<std::string>();

            if (process_id.empty())
            {
                res.status = 400;
                res.set_content(R"({"error":"Missing Process field"})", "application/json");
                return;
            }

            std::cout << "REST API: Start received, Process=" << process_id << std::endl;
            controller_->Start(process_id);
            res.set_content(R"({"status":"started"})", "application/json");
        });

        svr.Post("/operations/Stop", [this](const Request &, Response &res)
        {
            std::cout << "REST API: Stop received" << std::endl;
            controller_->Stop();
            res.set_content(R"({"status":"stopping"})", "application/json");
        });

        svr.Post("/operations/Reset", [this](const Request &, Response &res)
        {
            std::cout << "REST API: Reset received" << std::endl;
            controller_->Reset();
            res.set_content(R"({"status":"resetting"})", "application/json");
        });

        svr.Post("/operations/Abort", [this](const Request &, Response &res)
        {
            std::cout << "REST API: Abort received" << std::endl;
            controller_->Abort();
            res.set_content(R"({"status":"aborting"})", "application/json");
        });

        svr.Post("/operations/Clear", [this](const Request &, Response &res)
        {
            std::cout << "REST API: Clear received" << std::endl;
            controller_->Clear();
            res.set_content(R"({"status":"clearing"})", "application/json");
        });

        svr.Post("/operations/Hold", [this](const Request &, Response &res)
        {
            std::cout << "REST API: Hold received" << std::endl;
            controller_->Hold();
            res.set_content(R"({"status":"holding"})", "application/json");
        });

        svr.Post("/operations/Unhold", [this](const Request &, Response &res)
        {
            std::cout << "REST API: Unhold received" << std::endl;
            controller_->Unhold();
            res.set_content(R"({"status":"unholding"})", "application/json");
        });

        svr.Post("/operations/Suspend", [this](const Request &, Response &res)
        {
            std::cout << "REST API: Suspend received" << std::endl;
            controller_->Suspend();
            res.set_content(R"({"status":"suspending"})", "application/json");
        });

        svr.Post("/operations/Unsuspend", [this](const Request &, Response &res)
        {
            std::cout << "REST API: Unsuspend received" << std::endl;
            controller_->Unsuspend();
            res.set_content(R"({"status":"unsuspending"})", "application/json");
        });

        svr.Get("/health", [this](const Request &, Response &res)
        {
            res.set_content(
                R"({"status":"ok","running":)" +
                    std::string(controller_->isRunning() ? "true" : "false") + "}",
                "application/json");
        });

        std::cout << "Controller REST API listening on port " << port_ << std::endl;
        svr.listen("0.0.0.0", port_); });
}

void ControllerRestApi::stop()
{
    if (!running_)
        return;
    running_ = false;

    // httplib::Server::stop() is called implicitly when the server
    // goes out of scope in the thread lambda.  We join the thread.
    if (thread_.joinable())
        thread_.join();
}
