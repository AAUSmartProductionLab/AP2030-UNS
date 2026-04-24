// Unit tests for the bt_exec_refs parsing utilities introduced in PR2.

#include <gtest/gtest.h>

#include "bt/execution_refs.h"

using namespace bt_exec_refs;

TEST(ParseArgsList, EmptyAndWhitespace)
{
    EXPECT_TRUE(parseArgsList("").empty());
    EXPECT_TRUE(parseArgsList("   ").empty());
    EXPECT_TRUE(parseArgsList("\"\"").empty());
}

TEST(ParseArgsList, QuotedSemicolonSeparated)
{
    auto out = parseArgsList("\"{Param_a};{Param_b}\"");
    ASSERT_EQ(out.size(), 2u);
    EXPECT_EQ(out[0], "{Param_a}");
    EXPECT_EQ(out[1], "{Param_b}");
}

TEST(ParseArgsList, PlainSemicolonSeparated)
{
    auto out = parseArgsList("a;b;c");
    ASSERT_EQ(out.size(), 3u);
    EXPECT_EQ(out[0], "a");
    EXPECT_EQ(out[1], "b");
    EXPECT_EQ(out[2], "c");
}

TEST(ParseArgsList, SingleToken)
{
    auto out = parseArgsList("\"only-one\"");
    ASSERT_EQ(out.size(), 1u);
    EXPECT_EQ(out[0], "only-one");
}

TEST(StripWrappingQuotes, OnlyOuterLayer)
{
    EXPECT_EQ(stripWrappingQuotes("\"abc\""), "abc");
    // Inner quotes preserved.
    EXPECT_EQ(stripWrappingQuotes("\"a\"b\""), "a\"b");
    EXPECT_EQ(stripWrappingQuotes("abc"), "abc");
}

TEST(DecodeHtmlEntities, KnownEntities)
{
    EXPECT_EQ(decodeHtmlEntities("a&quot;b"), "a\"b");
    EXPECT_EQ(decodeHtmlEntities("&lt;tag&gt;"), "<tag>");
    EXPECT_EQ(decodeHtmlEntities("a&amp;b"), "a&b");
    EXPECT_EQ(decodeHtmlEntities("plain"), "plain");
}

TEST(ParseActionRef, RawJson)
{
    const std::string raw = R"({
        "source_aas_id": "https://example.org/aas/Dispenser",
        "action_aas_path": "Capabilities/Dispense",
        "transformation_aas_path": "Capabilities/Dispense/Transformation",
        "parameter_refs": [
            {"name": "Param_dosing", "aas_id": "https://example.org/aas/Vial",
             "aas_path": "Variables/Vial1"}
        ],
        "object_refs": {"Param_dosing": "Vial1"}
    })";
    auto ref = parseActionRef(raw);
    ASSERT_TRUE(ref.has_value());
    EXPECT_EQ(ref->source_aas_id, "https://example.org/aas/Dispenser");
    EXPECT_EQ(ref->action_aas_path, "Capabilities/Dispense");
    EXPECT_EQ(ref->transformation_aas_path, "Capabilities/Dispense/Transformation");
    ASSERT_EQ(ref->parameter_refs.size(), 1u);
    EXPECT_EQ(ref->parameter_refs[0].name, "Param_dosing");
    EXPECT_EQ(ref->parameter_refs[0].aas_path, "Variables/Vial1");
}

TEST(ParseActionRef, HtmlEntityEncodedJson)
{
    const std::string raw =
        "{&quot;source_aas_id&quot;:&quot;asset&quot;,"
        "&quot;action_aas_path&quot;:&quot;Capabilities/Run&quot;,"
        "&quot;transformation_aas_path&quot;:&quot;Capabilities/Run/Transformation&quot;,"
        "&quot;parameter_refs&quot;:[]}";
    auto ref = parseActionRef(raw);
    ASSERT_TRUE(ref.has_value());
    EXPECT_EQ(ref->source_aas_id, "asset");
    EXPECT_EQ(ref->action_aas_path, "Capabilities/Run");
}

TEST(ParseActionRef, MalformedReturnsNullopt)
{
    EXPECT_FALSE(parseActionRef("{ not-json").has_value());
    EXPECT_FALSE(parseActionRef("\"just a string\"").has_value());
    EXPECT_FALSE(parseActionRef("").has_value());
}

TEST(ParsePredicateRef, RawJson)
{
    const std::string raw = R"({
        "source_aas_id": "https://example.org/aas/Sensor",
        "fluent_aas_path": "Variables/Occupied",
        "transformation_aas_path": "Capabilities/Occupied/Transformation",
        "parameter_refs": []
    })";
    auto ref = parsePredicateRef(raw);
    ASSERT_TRUE(ref.has_value());
    EXPECT_EQ(ref->fluent_aas_path, "Variables/Occupied");
    EXPECT_EQ(ref->transformation_aas_path, "Capabilities/Occupied/Transformation");
}

// ----- splitSubmodelPath ----------------------------------------------------

TEST(SplitSubmodelPath, AIPlanningWithHyphenIsCanonicalized)
{
    auto [submodel, remainder] =
        splitSubmodelPath("AI-Planning/Domain/Fluents/Free/Transformation");
    EXPECT_EQ(submodel, "AIPlanning");
    EXPECT_EQ(remainder, "Domain/Fluents/Free/Transformation");
}

TEST(SplitSubmodelPath, AIPlanningCamelCasePassesThrough)
{
    auto [submodel, remainder] =
        splitSubmodelPath("AIPlanning/Domain/Actions/Loading");
    EXPECT_EQ(submodel, "AIPlanning");
    EXPECT_EQ(remainder, "Domain/Actions/Loading");
}

TEST(SplitSubmodelPath, KnownSubmodelPassesThrough)
{
    auto [submodel, remainder] = splitSubmodelPath("Skills/Loading/Loading");
    EXPECT_EQ(submodel, "Skills");
    EXPECT_EQ(remainder, "Loading/Loading");
}

TEST(SplitSubmodelPath, EmptyInputYieldsEmptyResult)
{
    auto [submodel, remainder] = splitSubmodelPath("");
    EXPECT_EQ(submodel, "");
    EXPECT_EQ(remainder, "");
}

TEST(SplitSubmodelPath, NoSlashYieldsRemainderOnly)
{
    auto [submodel, remainder] = splitSubmodelPath("AIPlanning");
    EXPECT_EQ(submodel, "");
    EXPECT_EQ(remainder, "AIPlanning");
}

TEST(SplitSubmodelPath, UnknownPrefixReturnsEmptySubmodel)
{
    auto [submodel, remainder] = splitSubmodelPath("Foo/Bar/Baz");
    EXPECT_EQ(submodel, "");
    EXPECT_EQ(remainder, "Foo/Bar/Baz");
}

// ----- PR4: GroundedAtom parsing & ActionRef.effects ------------------------

TEST(ParseGroundedAtomList, EmptyInputReturnsEmptyVector)
{
    auto out = parseGroundedAtomList("");
    ASSERT_TRUE(out.has_value());
    EXPECT_TRUE(out->empty());
}

TEST(ParseGroundedAtomList, ParsesArrayOfBoolAtoms)
{
    const std::string raw = R"([
        {"predicate": "step_ready", "args": ["order_product", "step_1_loading"], "value": true},
        {"predicate": "step_done",  "args": ["order_product", "step_1_loading"], "value": false}
    ])";
    auto out = parseGroundedAtomList(raw);
    ASSERT_TRUE(out.has_value());
    ASSERT_EQ(out->size(), 2u);
    EXPECT_EQ((*out)[0].predicate, "step_ready");
    EXPECT_EQ((*out)[0].args, (std::vector<std::string>{"order_product", "step_1_loading"}));
    EXPECT_EQ((*out)[0].value, true);
    EXPECT_EQ((*out)[1].predicate, "step_done");
    EXPECT_EQ((*out)[1].value, false);
}

TEST(ParseGroundedAtomList, MissingValueDefaultsToTrue)
{
    const std::string raw = R"([{"predicate":"p","args":["a"]}])";
    auto out = parseGroundedAtomList(raw);
    ASSERT_TRUE(out.has_value());
    ASSERT_EQ(out->size(), 1u);
    EXPECT_EQ((*out)[0].value, true);
}

TEST(ParseGroundedAtomList, MissingPredicateIsSkipped)
{
    const std::string raw = R"([
        {"args":["a"],"value":true},
        {"predicate":"p","args":["b"]}
    ])";
    auto out = parseGroundedAtomList(raw);
    ASSERT_TRUE(out.has_value());
    ASSERT_EQ(out->size(), 1u);
    EXPECT_EQ((*out)[0].predicate, "p");
}

TEST(ParseGroundedAtomList, MalformedJsonReturnsNullopt)
{
    EXPECT_FALSE(parseGroundedAtomList("{not-json").has_value());
}

TEST(ParseGroundedAtomList, NonArrayReturnsNullopt)
{
    EXPECT_FALSE(parseGroundedAtomList("{\"predicate\":\"x\"}").has_value());
}

TEST(ParseGroundedAtomList, HtmlEntityEncodedJsonAccepted)
{
    const std::string raw = "[{&quot;predicate&quot;:&quot;step_done&quot;,"
                            "&quot;args&quot;:[&quot;p&quot;,&quot;s&quot;],"
                            "&quot;value&quot;:true}]";
    auto out = parseGroundedAtomList(raw);
    ASSERT_TRUE(out.has_value());
    ASSERT_EQ(out->size(), 1u);
    EXPECT_EQ((*out)[0].predicate, "step_done");
    EXPECT_EQ((*out)[0].args, (std::vector<std::string>{"p", "s"}));
}

TEST(ParseActionRef, EffectsFieldDecoded)
{
    const std::string raw = R"({
        "source_aas_id": "asset",
        "action_aas_path": "AI-Planning/Domain/Actions/Dispense",
        "transformation_aas_path": "",
        "parameter_refs": [],
        "effects": [
            {"predicate":"step_done","args":["order_product","step_2"],"value":true},
            {"predicate":"step_ready","args":["order_product","step_2"],"value":false}
        ]
    })";
    auto ref = parseActionRef(raw);
    ASSERT_TRUE(ref.has_value());
    ASSERT_EQ(ref->effects.size(), 2u);
    EXPECT_EQ(ref->effects[0].predicate, "step_done");
    EXPECT_EQ(ref->effects[0].value, true);
    EXPECT_EQ(ref->effects[1].predicate, "step_ready");
    EXPECT_EQ(ref->effects[1].value, false);
}

TEST(ParseActionRef, MissingEffectsFieldIsBackCompat)
{
    // PR3-era trees do not carry "effects"; parser must tolerate.
    const std::string raw = R"({
        "source_aas_id": "asset",
        "action_aas_path": "Capabilities/Run",
        "transformation_aas_path": "Capabilities/Run/Transformation",
        "parameter_refs": []
    })";
    auto ref = parseActionRef(raw);
    ASSERT_TRUE(ref.has_value());
    EXPECT_TRUE(ref->effects.empty());
}
