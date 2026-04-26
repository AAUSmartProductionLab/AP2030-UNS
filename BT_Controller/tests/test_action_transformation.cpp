// Unit tests for the JSONata-based action message transformation pipeline
// used by ExecuteAction.
//
// These tests exercise the contract documented in the per-action
// `transformation:` YAML field and registered as the AAS String Property
// at AIPlanning/Domain/Actions/<ActionKey>/Transformation. The contract:
//
//   1. The JSONata expression is evaluated against the context object
//          { args, params, constants, object_refs, now, uuid }
//      where `params[i]` is the flattened `{idShort: value}` snapshot of
//      the i-th parameter AAS (Parameters and optionally Variables).
//
//   2. The expression returns a JSON object that is published verbatim
//      as the MQTT input message for the action.
//
//   3. If the expression's output omits a `Uuid` field, the runtime
//      injects the auto-generated fallback so the BT can correlate the
//      MQTT response. If it provides a `Uuid`, that value is what the BT
//      will match the response against.
//
//   4. The assembled message must validate against the action's input
//      JSON schema (resolved via AssetInterfaceDescription) before
//      publish; otherwise the action node fails without publishing.
//
// We assert all four properties using the same JSONata engine and
// schema-validator library that ExecuteAction uses at runtime.

#include <gtest/gtest.h>
#include <jsonata/Jsonata.h>
#include <nlohmann/json-schema.hpp>
#include <nlohmann/json.hpp>

#include <string>

namespace
{
    // Mirrors the post-eval merge logic in ExecuteAction::createMessage:
    // adopt the JSONata result verbatim, then ensure the message carries a
    // non-empty Uuid string. Returns the (possibly updated) effective uuid.
    std::string finalizeMessage(nlohmann::json &message, const std::string &fallback_uuid)
    {
        std::string current_uuid = fallback_uuid;
        if (!message.contains("Uuid") || !message["Uuid"].is_string() ||
            message["Uuid"].get<std::string>().empty())
        {
            message["Uuid"] = current_uuid;
        }
        else
        {
            current_uuid = message["Uuid"].get<std::string>();
        }
        return current_uuid;
    }

    nlohmann::json runTransformation(const std::string &expression,
                                     const nlohmann::json &context)
    {
        jsonata::Jsonata expr(expression);
        auto data = nlohmann::ordered_json::parse(context.dump());
        auto result = expr.evaluate(data);
        return nlohmann::json::parse(nlohmann::json(result).dump());
    }
} // namespace

// ---------------------------------------------------------------------------
// Context shape
// ---------------------------------------------------------------------------

TEST(ActionTransformation, ReadsArgsConstantsAndNow)
{
    const nlohmann::json context = {
        {"args", nlohmann::json::array({"product-1", "loadingStation"})},
        {"params", nlohmann::json::array()},
        {"constants", {{"speed", 42}, {"mode", "fast"}}},
        {"object_refs", nlohmann::json::object()},
        {"now", "2026-04-26T10:00:00Z"},
        {"uuid", "fallback-uuid-0001"},
    };

    auto out = runTransformation(
        R"({"Product": args[0], "Speed": constants.speed, "When": now})",
        context);

    EXPECT_EQ(out["Product"], "product-1");
    EXPECT_EQ(out["Speed"], 42);
    EXPECT_EQ(out["When"], "2026-04-26T10:00:00Z");
}

TEST(ActionTransformation, ReadsParameterParametersAndVariables)
{
    // params[0] is the IMA dispenser, params[1] is a Product whose UUID
    // we want to forward as the message Uuid (matches the YAML example
    // `'{"Uuid": params[1].Parameters.Uuid}'`).
    const nlohmann::json context = {
        {"args", nlohmann::json::array()},
        {"params", nlohmann::json::array({
                       {{"Parameters", {{"name", "ima-dispenser"}}}},
                       {{"Parameters", {{"Uuid", "product-uuid-xyz"}, {"Mass", 12.5}}},
                        {"Variables", {{"FillLevel", 0.83}}}},
                   })},
        {"constants", nlohmann::json::object()},
        {"object_refs", nlohmann::json::object()},
        {"now", "2026-04-26T10:00:00Z"},
        {"uuid", "fallback-uuid-0002"},
    };

    auto out = runTransformation(
        R"({"Uuid": params[1].Parameters.Uuid, "Mass": params[1].Parameters.Mass, "Fill": params[1].Variables.FillLevel})",
        context);

    EXPECT_EQ(out["Uuid"], "product-uuid-xyz");
    EXPECT_DOUBLE_EQ(out["Mass"].get<double>(), 12.5);
    EXPECT_DOUBLE_EQ(out["Fill"].get<double>(), 0.83);
}

// ---------------------------------------------------------------------------
// Uuid override / fallback semantics
// ---------------------------------------------------------------------------

TEST(ActionTransformation, UuidOverrideFromParameter)
{
    const nlohmann::json context = {
        {"args", nlohmann::json::array()},
        {"params", nlohmann::json::array({
                       {{"Parameters", {{"name", "dispenser"}}}},
                       {{"Parameters", {{"Uuid", "product-uuid-xyz"}}}},
                   })},
        {"constants", nlohmann::json::object()},
        {"object_refs", nlohmann::json::object()},
        {"now", "2026-04-26T10:00:00Z"},
        {"uuid", "fallback-uuid-aaaa"},
    };

    auto message = runTransformation(R"({"Uuid": params[1].Parameters.Uuid})", context);
    auto effective_uuid = finalizeMessage(message, "fallback-uuid-aaaa");

    EXPECT_EQ(message["Uuid"], "product-uuid-xyz");
    EXPECT_EQ(effective_uuid, "product-uuid-xyz")
        << "current_uuid_ must follow the published Uuid for response correlation";
}

TEST(ActionTransformation, UuidFallbackInjectedWhenTransformationOmits)
{
    const nlohmann::json context = {
        {"args", nlohmann::json::array({"value"})},
        {"params", nlohmann::json::array()},
        {"constants", nlohmann::json::object()},
        {"object_refs", nlohmann::json::object()},
        {"now", "2026-04-26T10:00:00Z"},
        {"uuid", "fallback-uuid-bbbb"},
    };

    auto message = runTransformation(R"({"Payload": args[0]})", context);
    auto effective_uuid = finalizeMessage(message, "fallback-uuid-bbbb");

    EXPECT_EQ(message["Uuid"], "fallback-uuid-bbbb");
    EXPECT_EQ(effective_uuid, "fallback-uuid-bbbb");
    EXPECT_EQ(message["Payload"], "value");
}

TEST(ActionTransformation, UuidFallbackInjectedWhenTransformationProducesEmptyString)
{
    // Defensive: a JSONata expression that emits an empty Uuid must not
    // pass through silently, otherwise the BT will never match a response.
    const nlohmann::json context = {
        {"args", nlohmann::json::array()},
        {"params", nlohmann::json::array()},
        {"constants", nlohmann::json::object()},
        {"object_refs", nlohmann::json::object()},
        {"now", "2026-04-26T10:00:00Z"},
        {"uuid", "fallback-uuid-cccc"},
    };

    auto message = runTransformation(R"({"Uuid": ""})", context);
    auto effective_uuid = finalizeMessage(message, "fallback-uuid-cccc");

    EXPECT_EQ(message["Uuid"], "fallback-uuid-cccc");
    EXPECT_EQ(effective_uuid, "fallback-uuid-cccc");
}

// ---------------------------------------------------------------------------
// Schema validation (Phase B')
// ---------------------------------------------------------------------------

TEST(ActionTransformation, SchemaValidationAcceptsConformingMessage)
{
    nlohmann::json schema = R"({
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "required": ["Uuid", "Mass"],
        "properties": {
            "Uuid": {"type": "string", "minLength": 1},
            "Mass": {"type": "number", "minimum": 0}
        }
    })"_json;

    nlohmann::json_schema::json_validator validator;
    ASSERT_NO_THROW(validator.set_root_schema(schema));

    nlohmann::json message = {{"Uuid", "abc"}, {"Mass", 12.5}};
    EXPECT_NO_THROW(validator.validate(message));
}

TEST(ActionTransformation, SchemaValidationRejectsMissingRequiredField)
{
    nlohmann::json schema = R"({
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "required": ["Uuid", "Mass"],
        "properties": {
            "Uuid": {"type": "string"},
            "Mass": {"type": "number"}
        }
    })"_json;

    nlohmann::json_schema::json_validator validator;
    validator.set_root_schema(schema);

    // Mass missing → must be rejected so ExecuteAction can refuse to publish.
    nlohmann::json message = {{"Uuid", "abc"}};
    EXPECT_THROW(validator.validate(message), std::exception);
}

TEST(ActionTransformation, SchemaValidationRejectsWrongType)
{
    nlohmann::json schema = R"({
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {
            "Mass": {"type": "number"}
        }
    })"_json;

    nlohmann::json_schema::json_validator validator;
    validator.set_root_schema(schema);

    nlohmann::json message = {{"Mass", "not-a-number"}};
    EXPECT_THROW(validator.validate(message), std::exception);
}

// End-to-end: transformation output validates against an action input
// schema describing the YAML example.
TEST(ActionTransformation, EndToEndDispensingMessageValidates)
{
    const nlohmann::json context = {
        {"args", nlohmann::json::array()},
        {"params", nlohmann::json::array({
                       {{"Parameters", {{"name", "ima-dispenser"}}}},
                       {{"Parameters", {{"Uuid", "p-42"}, {"TargetMass", 5.0}}}},
                   })},
        {"constants", nlohmann::json::object()},
        {"object_refs", nlohmann::json::object()},
        {"now", "2026-04-26T10:00:00Z"},
        {"uuid", "fallback"},
    };

    auto message = runTransformation(
        R"({"Uuid": params[1].Parameters.Uuid, "TargetMass": params[1].Parameters.TargetMass})",
        context);
    finalizeMessage(message, "fallback");

    nlohmann::json schema = R"({
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "required": ["Uuid", "TargetMass"],
        "properties": {
            "Uuid": {"type": "string", "minLength": 1},
            "TargetMass": {"type": "number", "exclusiveMinimum": 0}
        }
    })"_json;

    nlohmann::json_schema::json_validator validator;
    validator.set_root_schema(schema);

    EXPECT_EQ(message["Uuid"], "p-42");
    EXPECT_DOUBLE_EQ(message["TargetMass"].get<double>(), 5.0);
    EXPECT_NO_THROW(validator.validate(message));
}
