// Unit tests for the new compact execution-ref format (URLs + JSON arrays).

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

TEST(ParseJsonStringArray, Empty)
{
    EXPECT_TRUE(parseJsonStringArray("").empty());
}

TEST(ParseJsonStringArray, ParsesArray)
{
    auto out = parseJsonStringArray(R"(["aas://x","aas://y"])");
    ASSERT_EQ(out.size(), 2u);
    EXPECT_EQ(out[0], "aas://x");
    EXPECT_EQ(out[1], "aas://y");
}

TEST(ParseJsonStringArray, HtmlEntityEncoded)
{
    auto out = parseJsonStringArray("[&quot;aas://z&quot;]");
    ASSERT_EQ(out.size(), 1u);
    EXPECT_EQ(out[0], "aas://z");
}

TEST(ParseActionRef, UrlFormat)
{
    const std::string url =
        "https://example.org/submodels/instances/myDispenserAAS/Skills/Dispense";
    auto ref = parseActionRef(url);
    ASSERT_TRUE(ref.has_value());
    EXPECT_EQ(ref->skill_url, url);
    EXPECT_EQ(ref->source_aas_id, "myDispenserAAS");
    EXPECT_EQ(ref->skill_name, "Dispense");
}

TEST(ParseActionRef, UrlWithTrailingSlash)
{
    auto ref = parseActionRef(
        "https://host/submodels/instances/Asset123/Skills/Loading/");
    ASSERT_TRUE(ref.has_value());
    EXPECT_EQ(ref->source_aas_id, "Asset123");
    EXPECT_EQ(ref->skill_name, "Loading");
}

TEST(ParseActionRef, BackwardCompatJson)
{
    const std::string raw = R"({
        "source_aas_id": "https://example.org/aas/Dispenser",
        "skill_name": "Dispense"
    })";
    auto ref = parseActionRef(raw);
    ASSERT_TRUE(ref.has_value());
    EXPECT_EQ(ref->source_aas_id, "https://example.org/aas/Dispenser");
    EXPECT_EQ(ref->skill_name, "Dispense");
}

TEST(ParseActionRef, EmptyReturnsNullopt)
{
    EXPECT_FALSE(parseActionRef("").has_value());
    EXPECT_FALSE(parseActionRef("\"\"").has_value());
}

TEST(ParseFluentRef, PlainUri)
{
    auto ref = parseFluentRef("https://w3id.org/2026/apex/Free");
    ASSERT_TRUE(ref.has_value());
    EXPECT_EQ(ref->fluent_uri, "https://w3id.org/2026/apex/Free");
    EXPECT_TRUE(ref->args.empty());
}

TEST(ParseFluentRef, BackwardCompatJson)
{
    const std::string raw = R"({
        "predicate": "free",
        "semantic_id": "https://w3id.org/2026/apex/Free",
        "args": ["shuttle1"]
    })";
    auto ref = parseFluentRef(raw);
    ASSERT_TRUE(ref.has_value());
    EXPECT_EQ(ref->fluent_uri, "https://w3id.org/2026/apex/Free");
    ASSERT_EQ(ref->args.size(), 1u);
    EXPECT_EQ(ref->args[0], "shuttle1");
}

TEST(ParseFluentRef, BackwardCompatJsonFallsBackToPredicate)
{
    auto ref = parseFluentRef(R"({"predicate":"step_done","args":["p","s"]})");
    ASSERT_TRUE(ref.has_value());
    EXPECT_EQ(ref->fluent_uri, "step_done");
    ASSERT_EQ(ref->args.size(), 2u);
}

TEST(ParseFluentRef, EmptyReturnsNullopt)
{
    EXPECT_FALSE(parseFluentRef("").has_value());
}

TEST(StripWrappingQuotes, OnlyOuterLayer)
{
    EXPECT_EQ(stripWrappingQuotes("\"abc\""), "abc");
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

TEST(SplitSubmodelPath, AIPlanningWithHyphenCanonicalized)
{
    auto [submodel, remainder] =
        splitSubmodelPath("AI-Planning/Domain/Fluents/Free/Transformation");
    EXPECT_EQ(submodel, "AIPlanning");
    EXPECT_EQ(remainder, "Domain/Fluents/Free/Transformation");
}

TEST(SplitSubmodelPath, KnownSubmodelPassesThrough)
{
    auto [submodel, remainder] = splitSubmodelPath("Skills/Loading/Loading");
    EXPECT_EQ(submodel, "Skills");
    EXPECT_EQ(remainder, "Loading/Loading");
}

TEST(SplitSubmodelPath, EmptyInputYieldsEmpty)
{
    auto [s, r] = splitSubmodelPath("");
    EXPECT_EQ(s, "");
    EXPECT_EQ(r, "");
}

TEST(SplitSubmodelPath, NoSlashIsRemainder)
{
    auto [s, r] = splitSubmodelPath("AIPlanning");
    EXPECT_EQ(s, "");
    EXPECT_EQ(r, "AIPlanning");
}
