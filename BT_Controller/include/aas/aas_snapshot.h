#pragma once

#include <optional>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

#include "aas/aas_client.h"
#include "bt/execution_refs.h"

/// Helpers shared by FluentCheck and ExecuteAction for assembling the
/// JSONata evaluation context out of an AAS. Both nodes need the same
/// per-parameter snapshot ({Parameters, Variables}) and the same sibling
/// ``Constants`` SMC fetched alongside the ``Transformation`` Property.
namespace aas_snapshot
{
    /// Coerce an AAS Property's stringified ``value`` into the JSONata-friendly
    /// type implied by ``valueType``. AAS REST always serializes property
    /// values as strings; transformations expect proper numbers and booleans.
    nlohmann::json coerceProperty(const nlohmann::json &elem);

    /// Recursively flatten an AAS submodel/SMC/Property/SubmodelElementList
    /// into idiomatic JSON: SMCs and Submodels become objects keyed by child
    /// idShort; SubmodelElementLists become arrays; Properties collapse to
    /// their typed value.
    nlohmann::json flattenAasElement(const nlohmann::json &elem);

    /// Return the parent of a slash-separated AAS path (drops the last
    /// segment). Used to address a sibling SMC like ``Constants`` that
    /// lives next to a ``Transformation`` Property.
    std::string parentSlashPath(const std::string &slash_path);

    /// Extract the value of the *last* Key in a ReferenceElement's
    /// ``value.keys`` array. Returns nullopt if the element is malformed.
    std::optional<std::string> lastKeyValue(const nlohmann::json &reference_element);

    /// Pre-fetch each parameter's static Parameters submodel and (if
    /// requested) its raw Variables submodel for the JSONata
    /// ``params[i]`` slot. Failures to fetch a submodel are tolerated —
    /// the corresponding entry stays an empty object so the
    /// transformation can still surface a useful error.
    ///
    /// When ``raw_variables`` is non-null and ``include_variables`` is
    /// true, the raw Variables submodel JSON for each parameter is also
    /// returned (parallel index to the result vector). The caller can
    /// use it to register MQTT subscriptions per-Variable.
    std::vector<nlohmann::json> fetchParamSnapshots(
        AASClient &aas_client,
        const std::vector<bt_exec_refs::ParameterRef> &parameter_refs,
        bool include_variables,
        std::vector<std::optional<nlohmann::json>> *raw_variables = nullptr);

    /// Pre-fetch the ``Constants`` SMC sibling of ``transformation_aas_path``
    /// and flatten it to ``{name: typed_value}``. Returns an empty object
    /// when the source aas_id or transformation path are empty, when the
    /// path has no parent, or when the sibling SMC does not exist.
    nlohmann::json fetchSiblingConstants(
        AASClient &aas_client,
        const std::string &source_aas_id,
        const std::string &transformation_aas_path);
}
