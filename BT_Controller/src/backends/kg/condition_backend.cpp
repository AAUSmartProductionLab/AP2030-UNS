#include "backends/kg/condition_backend.h"
#include "backends/kg/kg_query_client.h"

KgConditionBackend::KgConditionBackend(KgClient &client)
    : client_(client) {}

bool KgConditionBackend::isConfigured() const
{
    return client_.isConfigured();
}

std::optional<bool> KgConditionBackend::evaluate(
    const std::string &predicate_name,
    const std::vector<std::string> &args)
{
    return client_.askPredicate(predicate_name, args);
}
