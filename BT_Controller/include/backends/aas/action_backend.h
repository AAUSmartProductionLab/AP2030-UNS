#pragma once

#include "backends/action_backend.h"
#include <memory>
#include <string>
#include <vector>

class BindingResolver;
class AASClient;
namespace bt_exec_refs
{
    struct ActionRef;
}

/// Synchronous AAS action backend.  Resolves parameters via BindingResolver,
/// invokes the skill via AASClient::invokeOperation(), returns
/// SUCCESS/FAILURE.
class AasActionBackend : public IActionBackend
{
public:
    AasActionBackend(BindingResolver &resolver,
                     AASClient &aas_client);

    BT::NodeStatus onStart(const ActionContext &ctx) override;
    BT::NodeStatus onRunning() override;
    void onHalted() override;
    nlohmann::json responseData() const override;
    bool isConfigured() const override;
    std::string backendName() const override { return "AAS"; }

private:
    BindingResolver &resolver_;
    AASClient &aas_client_;
    nlohmann::json last_response_;
};
