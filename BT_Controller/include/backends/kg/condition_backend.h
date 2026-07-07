#pragma once

#include "backends/condition_backend.h"

class KgClient;

/// KG-backed condition backend.  Sends a SPARQL ASK query via
/// KgClient and returns the boolean result.
class KgConditionBackend : public IConditionBackend
{
public:
    explicit KgConditionBackend(KgClient &client);

    std::optional<bool> evaluate(const std::string &predicate_name,
                                 const std::vector<std::string> &args) override;
    bool isConfigured() const override;
    std::string backendName() const override { return "KG"; }

private:
    KgClient &client_;
};
