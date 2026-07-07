#pragma once

#include "backends/condition_backend.h"

class AASClient;

/// AAS condition backend.  Reads Variable submodel elements directly
/// via AASClient::fetchPropertyValue.
class AasConditionBackend : public IConditionBackend
{
public:
    explicit AasConditionBackend(AASClient &aas_client);

    std::optional<bool> evaluate(const std::string &predicate_name,
                                 const std::vector<std::string> &args) override;
    bool isConfigured() const override { return true; }
    std::string backendName() const override { return "AAS"; }

private:
    AASClient &aas_client_;
};
