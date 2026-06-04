from __future__ import annotations

import json
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


def test_materialization_runner_skips_rules_by_prefix(tmp_path: Path):
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "010-a.rq").write_text("INSERT DATA { <urn:a> <urn:p> <urn:o> . }", encoding="utf-8")
    (rules_dir / "040-b.rq").write_text("INSERT DATA { <urn:b> <urn:p> <urn:o> . }", encoding="utf-8")

    runner = MaterializationRunner(
        str(rules_dir),
        enabled=True,
        disabled_rule_prefixes=("010-",),
    )
    client = _FakeSparqlClient()

    runner.apply(client)

    assert len(client.executed) == 1
    assert "urn:b" in client.executed[0]


def test_shell_typing_rule_contains_expected_type_derivations():
    rule_path = Path(__file__).resolve().parents[1] / "sparql" / "materialization" / "020-aas-shell-typing.rq"
    text = rule_path.read_text(encoding="utf-8")

    # Product/ProcessAssetAdministrationShell types are now assigned directly by
    # the bridge projection — rule 020 no longer derives them from entity links.
    assert "{{ABOX_GRAPH_N3}}" in text
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
    assert "aas-rel:first" in text
    assert "aas-rel:second" in text
    assert "aas-rfb:idShort" in text
    assert "https://admin-shell.io/idta/CapabilityDescription/CapabilityRealizedBy/1/0" in text


def test_action_projection_rule_contains_expected_structure():
    rule_path = Path(__file__).resolve().parents[1] / "sparql" / "materialization" / "040-apex-action-projection.rq"
    text = rule_path.read_text(encoding="utf-8")

    assert "{{ABOX_GRAPH_N3}}" in text
    assert "apex:Action" in text
    assert "apex:sourceSemanticId" in text
    assert "apex:hasSourceAAS" in text
    assert "apex:TemporalProcess" in text
    assert "apex:TemporalEvent" in text
    # Path format relative to submodel root: Domain prefix, named-key paths (not indexed AI-Planning.Domain.Actions[N]).
    # SPARQL regex strings double-escape dots, so check section comment markers for readability.
    assert "Actions" in text and "Processes" in text and "Events" in text
    assert "Domain" in text
    assert "AI-Planning" not in text  # old wrong prefix must be absent
    # Identity IRI strategy: single literal /submodel-elements/ separator, no %2F dual-handling.
    assert "/submodel-elements/" in text
    assert "%2Fsubmodel-elements%2F" not in text
    # RefKey data used for full condition/effect projection
    assert "apex:hasRefKey" in text
    assert "apex:constraintArg" in text


def test_apex_pddl_module_contains_parameter_projection_terms():
    ontology_path = Path(__file__).resolve().parents[1] / "Ontology" / "APEX" / "apex-pddl.ttl"
    text = ontology_path.read_text(encoding="utf-8")

    assert "apex:Parameter" in text
    assert "apex:parameterIndex" in text
    assert "apex:parameterTypeRef" in text
    assert "apex:skillReferenceKey" in text


def test_apex_core_contains_mirrored_sm_element_semantic_id_property():
    ontology_path = Path(__file__).resolve().parents[1] / "Ontology" / "APEX" / "apex.ttl"
    text = ontology_path.read_text(encoding="utf-8")

    assert "apex:smElementSemanticId" in text


def test_apex_shacl_module_contains_phase2_structural_gate_shapes():
    ontology_path = Path(__file__).resolve().parents[1] / "Ontology" / "APEX" / "apex-shacl.ttl"
    text = ontology_path.read_text(encoding="utf-8")

    assert "apex:ResourceLocationShape" in text
    assert "apex:PredicateDefinitionShape" in text
    assert "apex:ActionSkillReferenceShape" in text
    assert "apex:CppmBelongsToExactlyOneCppsShape" in text
    assert "apex:skillReferenceKey" in text
    assert "sh:inversePath apex:hasCPPM" in text


def test_apex_fond_module_contains_branch_projection_terms():
    ontology_path = Path(__file__).resolve().parents[1] / "Ontology" / "APEX" / "apex-fond.ttl"
    text = ontology_path.read_text(encoding="utf-8")

    assert "apex:EffectBranch" in text
    assert "apex:hasBranch" in text
    assert "apex:hasBranchEffect" in text
    assert "apex:branchGuard" in text


def test_apex_root_imports_trim_unused_language_variants():
    ontology_path = Path(__file__).resolve().parents[1] / "Ontology" / "APEX" / "apex.ttl"
    text = ontology_path.read_text(encoding="utf-8")

    assert "owl:imports <https://w3id.org/2026/apex/pddl>" in text
    assert "owl:imports <https://w3id.org/2026/apex/pddl-2-1>" in text
    assert "owl:imports <https://w3id.org/2026/apex/pddl-plus>" in text
    assert "owl:imports <https://w3id.org/2026/apex/fond>" in text
    assert "owl:imports <https://w3id.org/2026/apex/pddl-3>" not in text
    assert "owl:imports <https://w3id.org/2026/apex/ppddl>" not in text


def test_apex_resource_hierarchy_contains_skill_chain_axioms():
    ontology_path = Path(__file__).resolve().parents[1] / "Ontology" / "APEX" / "apex-resource-hierarchy.ttl"
    text = ontology_path.read_text(encoding="utf-8")

    assert "owl:propertyChainAxiom" in text
    assert "css:providesSkill" in text
    assert ":hasCPPM" in text
    assert ":hasCPS" in text


def test_apex_main_capabilities_extension_exists_and_is_additive():
    extension_path = (
        Path(__file__).resolve().parents[1]
        / "Ontology"
        / "APEX"
        / "extensions"
        / "apex-extension-main-capabilities.ttl"
    )
    text = extension_path.read_text(encoding="utf-8")

    assert "https://w3id.org/2026/apex/extensions/main-capabilities" in text
    assert "owl:imports <https://w3id.org/2026/apex/>" in text
    assert "apex:LoadingCapability" in text
    assert "apex:MoveToPositionCapability" in text


def test_arso_extensions_contains_shell_disjointness_axiom():
    ontology_path = Path(__file__).resolve().parents[1] / "Ontology" / "arso-extensions.ttl"
    text = ontology_path.read_text(encoding="utf-8")

    assert "owl:disjointWith arsox:ProcessAssetAdministrationShell" in text


def test_submodel_semantic_id_map_contract_has_required_entries():
    contract_path = Path(__file__).resolve().parents[1] / "contracts" / "submodel-semantic-id-map.phase2.json"
    payload = json.loads(contract_path.read_text(encoding="utf-8"))

    mappings = payload.get("mappings")
    assert isinstance(mappings, list)
    assert any(entry.get("semantic_id") == "https://admin-shell.io/idta/SubmodelTemplate/CapabilityDescription/1/0" for entry in mappings)
    assert any(entry.get("semantic_id") == "https://admin-shell.io/idta/ControlComponentType/1/0" for entry in mappings)


def test_predicate_dispatch_contract_is_semantic_id_first_with_fallback():
    contract_path = Path(__file__).resolve().parents[1] / "contracts" / "predicate-dispatch.phase0.yaml"
    text = contract_path.read_text(encoding="utf-8")

    assert "path_binding_mode: semantic_id" in text
    assert "semantic_id_with_regex_fallback" not in text
    assert "station_filter_regex" not in text
    assert "station_selection_mode: type_or_capability_with_idshort_fallback" in text
    assert "https://w3id.org/2026/apex/semantic/location/label" in text
    assert "https://w3id.org/2026/apex/semantic/state/occupied" in text
    assert "https://w3id.org/2026/apex/semantic/state/operational" in text
    assert "https://w3id.org/2026/apex/semantic/position/x" in text
    assert "https://w3id.org/2026/apex/semantic/position/y" in text
