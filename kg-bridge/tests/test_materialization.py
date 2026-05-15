from __future__ import annotations

from pathlib import Path

from runtime.materialization import MaterializationRunner


class _FakeSparqlClient:
    def __init__(self) -> None:
        self.executed: list[str] = []

    def update(self, statement: str) -> None:
        self.executed.append(statement)


def test_materialization_runner_loads_and_executes_rules(tmp_path: Path):
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "010-a.rq").write_text("INSERT DATA { <urn:a> <urn:p> <urn:o> . }", encoding="utf-8")
    (rules_dir / "020-b.rq").write_text("INSERT DATA { <urn:b> <urn:p> <urn:o> . }", encoding="utf-8")

    runner = MaterializationRunner(str(rules_dir), enabled=True)
    client = _FakeSparqlClient()

    assert runner.enabled is True

    runner.apply(client)

    assert len(client.executed) == 2
    assert "urn:a" in client.executed[0]
    assert "urn:b" in client.executed[1]


def test_materialization_runner_disabled_has_no_rules(tmp_path: Path):
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "010-a.rq").write_text("INSERT DATA { <urn:a> <urn:p> <urn:o> . }", encoding="utf-8")

    runner = MaterializationRunner(str(rules_dir), enabled=False)

    assert runner.enabled is False


def test_materialization_runner_renders_named_graph_template(tmp_path: Path):
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "010-a.rq").write_text(
        "WITH {{AAS_GRAPH_N3}} INSERT DATA { <urn:a> <urn:p> <urn:o> . } WHERE {}",
        encoding="utf-8",
    )

    runner = MaterializationRunner(str(rules_dir), enabled=True, graph_iri="urn:kg:aas")
    client = _FakeSparqlClient()

    runner.apply(client)

    assert len(client.executed) == 1
    assert "WITH <urn:kg:aas>" in client.executed[0]
    assert "{{AAS_GRAPH_N3}}" not in client.executed[0]


def test_materialization_runner_skips_unresolved_templates(tmp_path: Path):
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "010-a.rq").write_text("WITH {{AAS_GRAPH_N3}} INSERT DATA { <urn:a> <urn:p> <urn:o> . }", encoding="utf-8")

    runner = MaterializationRunner(str(rules_dir), enabled=True, graph_iri=None)

    assert runner.enabled is False


def test_materialization_runner_renders_named_graph_tokens(tmp_path: Path):
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "010-a.rq").write_text(
        "INSERT DATA { {{ABOX_GRAPH_N3}} <urn:p> {{TBOX_GRAPH_N3}} . {{SHACL_GRAPH_N3}} <urn:q> <urn:r> . }",
        encoding="utf-8",
    )

    runner = MaterializationRunner(
        str(rules_dir),
        enabled=True,
        abox_graph_iri="urn:kg:abox",
        tbox_graph_iri="urn:kg:tbox",
        shacl_graph_iri="urn:kg:shacl",
    )
    client = _FakeSparqlClient()

    runner.apply(client)

    assert len(client.executed) == 1
    assert "<urn:kg:abox>" in client.executed[0]
    assert "<urn:kg:tbox>" in client.executed[0]
    assert "<urn:kg:shacl>" in client.executed[0]


def test_shell_typing_rule_contains_expected_type_derivations():
    rule_path = Path(__file__).resolve().parents[1] / "sparql" / "materialization" / "020-aas-shell-typing.rq"
    text = rule_path.read_text(encoding="utf-8")

    assert "{{ABOX_GRAPH_N3}}" in text
    assert "arsox:ProductAssetAdministrationShell" in text
    assert "arsox:ProcessAssetAdministrationShell" in text
    assert "arso:HasOperationalDataAAS" in text
    assert "arso:HasParametersAAS" in text
    assert "arso:HasCapabilitiesAAS" in text
    assert "arso:HasSkillsAAS" in text
    assert "arso:HasSkillsFromCapabilitiesAAS" in text
    assert "arso:hasOperationalDataSubmodel" in text
    assert "arso:hasParametersSubmodel" in text
    assert "arso:hasCapabilitiesSubmodel" in text
    assert "arso:hasSkillsSubmodel" in text


def test_capability_skill_realization_rule_contains_expected_join_pattern():
    rule_path = Path(__file__).resolve().parents[1] / "sparql" / "materialization" / "030-capability-skill-realization.rq"
    text = rule_path.read_text(encoding="utf-8")

    assert "{{ABOX_GRAPH_N3}}" in text
    assert "css:isRealizedBySkill" in text
    assert "arso:hasCapabilitiesSubmodel" in text
    assert "arso:hasSkillsSubmodel" in text
    assert "aas:RelationshipElement/first" in text
    assert "aas:RelationshipElement/second" in text
    assert "aas:Referable/idShort" in text
    assert "https://admin-shell.io/idta/CapabilityDescription/CapabilityRealizedBy/1/0" in text
