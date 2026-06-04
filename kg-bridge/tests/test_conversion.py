"""Tests for kg-bridge conversion layer: IRI encoding, event parsing, SPARQL generation,
fixture-driven round-trip (G2/G8), idempotency (G3), and cascade boundary (G4)."""

from __future__ import annotations

import json
import pathlib

import pytest
import rdflib
from rdflib.compare import to_isomorphic

from conversion import event_to_sparql, parse_event, submodel_element_iri
from conversion.events import AasEvent, SubmodelEvent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
BASE_URI = "urn:kg:aas:"


def _apply(events: list[tuple[dict, str]], g: rdflib.Graph | None = None) -> rdflib.Graph:
    """Apply a sequence of (event_dict, topic) pairs to a Graph."""
    if g is None:
        g = rdflib.Graph()
    for ev_dict, topic in events:
        ev = parse_event(ev_dict, topic=topic)
        for stmt in event_to_sparql(ev, base_uri=BASE_URI, graph_iri=None, enable_projection=False):
            g.update(stmt)
    return g


def _load_fixture(path: pathlib.Path) -> tuple[rdflib.Graph, rdflib.Graph]:
    """Return (actual_graph, expected_graph) for a fixture JSON file."""
    data = json.loads(path.read_text())
    topic = data["topic"]
    ev_dict = data["event"]
    pre_events = [(p["event"], p["topic"]) for p in data.get("pre_events", [])]

    g = _apply(pre_events)
    ev = parse_event(ev_dict, topic=topic)
    for stmt in event_to_sparql(ev, base_uri=BASE_URI, graph_iri=None, enable_projection=False):
        g.update(stmt)

    expected_ttl_path = path.parent / (path.stem + ".expected.ttl")
    expected_g = rdflib.Graph()
    ttl = expected_ttl_path.read_text().strip()
    if ttl:
        expected_g.parse(data=ttl, format="turtle")

    return g, expected_g


# ---------------------------------------------------------------------------
# Existing unit tests (preserved)
# ---------------------------------------------------------------------------


def test_submodel_element_iri_encodes_list_indices():
    iri = submodel_element_iri(
        base_uri="urn:kg:aas:",
        submodel_id="https://aas.example.org/sm/1",
        sm_element_path="Col1.List1[1].P2",
    )
    assert str(iri).endswith(
        "https%3A%2F%2Faas.example.org%2Fsm%2F1%2Fsubmodel-elements%2FCol1.List1%5B1%5D.P2"
    )


def test_parse_event_uses_topic_discriminator():
    aas_event = parse_event({"type": "AAS_DELETED", "id": "urn:aas:1"}, topic="aas-events")
    sm_event = parse_event({"type": "SM_DELETED", "id": "urn:sm:1"}, topic="submodel-events")

    assert isinstance(aas_event, AasEvent)
    assert isinstance(sm_event, SubmodelEvent)


def test_event_to_sparql_sm_ref_added_generates_link():
    event = parse_event(
        {"type": "SM_REF_ADDED", "id": "urn:aas:1", "submodelId": "urn:sm:1"},
        topic="aas-events",
    )
    statements = event_to_sparql(event=event, base_uri="urn:kg:aas:", graph_iri=None, enable_projection=False)
    assert len(statements) == 1
    assert "INSERT DATA" in statements[0]
    assert "AssetAdministrationShell/submodels" in statements[0]


def test_event_to_sparql_sme_created_uses_path_target():
    event = parse_event(
        {
            "type": "SME_CREATED",
            "id": "https://aas.example.org/sm/1",
            "smElementPath": "Col1.List1[1].P2",
            "smElement": {"modelType": "Property", "idShort": "P2", "valueType": "xs:string", "value": "x"},
        },
        topic="submodel-events",
    )
    statements = event_to_sparql(event=event, base_uri="urn:kg:aas:", graph_iri=None, enable_projection=False)
    assert len(statements) == 1
    assert "DELETE" in statements[0]
    assert "INSERT" in statements[0]
    assert "Col1.List1%5B1%5D.P2" in statements[0]


def test_projection_sm_ref_added_emits_arso_has_submodel():
    event = parse_event(
        {"type": "SM_REF_ADDED", "id": "urn:aas:proj", "submodelId": "urn:sm:proj"},
        topic="aas-events",
    )

    statements = event_to_sparql(event=event, base_uri="urn:kg:aas:", graph_iri=None, enable_projection=True)
    joined = "\n".join(statements)

    assert "https://w3id.org/2025/arso#hasSubmodel" in joined


def test_projection_submodel_semantic_id_emits_arso_type_and_apex_semantic_literal():
    event = parse_event(
        {
            "type": "SM_CREATED",
            "id": "urn:sm:typed",
            "submodel": {
                "id": "urn:sm:typed",
                "semanticId": {
                    "type": "ExternalReference",
                    "keys": [
                        {
                            "type": "GlobalReference",
                            "value": "https://admin-shell.io/idta/SubmodelTemplate/CapabilityDescription/1/0",
                        }
                    ],
                },
            },
        },
        topic="submodel-events",
    )

    statements = event_to_sparql(event=event, base_uri="urn:kg:aas:", graph_iri=None, enable_projection=True)
    joined = "\n".join(statements)

    assert "https://w3id.org/2025/arso#CapabilitiesSubmodel" in joined
    assert "https://w3id.org/2026/apex/sourceSemanticId" in joined


def test_projection_sme_scalar_value_is_mirrored_in_apex():
    event = parse_event(
        {
            "type": "SME_CREATED",
            "id": "urn:sm:mirror",
            "smElementPath": "P1",
            "smElement": {
                "modelType": "Property",
                "idShort": "P1",
                "valueType": "xs:string",
                "value": "v1",
            },
        },
        topic="submodel-events",
    )

    statements = event_to_sparql(event=event, base_uri="urn:kg:aas:", graph_iri=None, enable_projection=True)
    joined = "\n".join(statements)

    assert "https://w3id.org/2026/apex/MirroredSubmodelElement" in joined
    assert "https://w3id.org/2026/apex/smElementPath" in joined
    assert "https://w3id.org/2026/apex/smElementValue" in joined


def test_projection_sme_semantic_id_is_mirrored_in_apex():
    event = parse_event(
        {
            "type": "SME_CREATED",
            "id": "urn:sm:mirror-semantic",
            "smElementPath": "Runtime.CurrentLocation",
            "smElement": {
                "modelType": "Property",
                "idShort": "CurrentLocation",
                "valueType": "xs:string",
                "value": "LoadingStation",
                "semanticId": {
                    "type": "ExternalReference",
                    "keys": [
                        {
                            "type": "GlobalReference",
                            "value": "https://w3id.org/2026/apex/semantic/location/label",
                        }
                    ],
                },
            },
        },
        topic="submodel-events",
    )

    statements = event_to_sparql(event=event, base_uri="urn:kg:aas:", graph_iri=None, enable_projection=True)
    joined = "\n".join(statements)

    assert "https://w3id.org/2026/apex/smElementSemanticId" in joined
    assert "https://w3id.org/2026/apex/semantic/location/label" in joined


def _insert_block(statements: list) -> str:
    """Extract only INSERT DATA statements to check what was actually asserted."""
    return "\n".join(s for s in statements if s and "INSERT DATA" in s)


def test_projection_aas_product_shell_typed_directly():
    """Product AAS gets arsox:ProductAssetAdministrationShell — no synthetic entity node."""
    stmts = event_to_sparql(
        event=parse_event(
            {"type": "AAS_CREATED", "id": "urn:aas:product:hgh",
             "aas": {"id": "urn:aas:product:hgh", "idShort": "ProductTwinHgH",
                     "assetInformation": {"assetKind": "Instance"}}},
            topic="aas-events"),
        base_uri="urn:kg:aas:", graph_iri=None, enable_projection=True)

    inserts = _insert_block(stmts)
    shell = "<urn:kg:aas:urn%3Aaas%3Aproduct%3Ahgh>"
    assert f"{shell} <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <https://w3id.org/aau-ra/arso-ext#ProductAssetAdministrationShell> ." in inserts
    assert "ProcessAssetAdministrationShell" not in inserts
    assert "ResourceAssetAdministrationShell" not in inserts


def test_projection_aas_process_shell_typed_directly():
    """Process AAS gets arsox:ProcessAssetAdministrationShell — no synthetic entity node."""
    stmts = event_to_sparql(
        event=parse_event(
            {"type": "AAS_CREATED", "id": "urn:aas:process:mixing",
             "aas": {"id": "urn:aas:process:mixing", "idShort": "ProcessTwin",
                     "assetInformation": {"assetKind": "Instance"}}},
            topic="aas-events"),
        base_uri="urn:kg:aas:", graph_iri=None, enable_projection=True)

    inserts = _insert_block(stmts)
    shell = "<urn:kg:aas:urn%3Aaas%3Aprocess%3Amixing>"
    assert f"{shell} <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <https://w3id.org/aau-ra/arso-ext#ProcessAssetAdministrationShell> ." in inserts
    assert "ProductAssetAdministrationShell" not in inserts
    assert "ResourceAssetAdministrationShell" not in inserts


def test_projection_aas_resource_shell_typed_directly():
    """Resource AAS gets arsox:ResourceAssetAdministrationShell — no synthetic entity node."""
    stmts = event_to_sparql(
        event=parse_event(
            {"type": "AAS_CREATED", "id": "urn:aas:resource:loading-station",
             "aas": {"id": "urn:aas:resource:loading-station", "idShort": "LoadingStationAAS",
                     "assetInformation": {"assetKind": "Instance"}}},
            topic="aas-events"),
        base_uri="urn:kg:aas:", graph_iri=None, enable_projection=True)

    inserts = _insert_block(stmts)
    shell = "<urn:kg:aas:urn%3Aaas%3Aresource%3Aloading-station>"
    assert f"{shell} <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <https://w3id.org/aau-ra/arso-ext#ResourceAssetAdministrationShell> ." in inserts
    assert "ProductAssetAdministrationShell" not in inserts
    assert "ProcessAssetAdministrationShell" not in inserts


def test_projection_aas_category_overrides_id_keyword():
    """Explicit category=product wins over process keyword in the AAS ID."""
    stmts = event_to_sparql(
        event=parse_event(
            {"type": "AAS_CREATED", "id": "urn:aas:process:looks-like-process",
             "aas": {"id": "urn:aas:process:looks-like-process",
                     "idShort": "ProcessTwinButCategoryProduct",
                     "category": "product",
                     "assetInformation": {"assetKind": "Instance"}}},
            topic="aas-events"),
        base_uri="urn:kg:aas:", graph_iri=None, enable_projection=True)

    inserts = _insert_block(stmts)
    shell = "<urn:kg:aas:urn%3Aaas%3Aprocess%3Alooks-like-process>"
    assert f"{shell} <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <https://w3id.org/aau-ra/arso-ext#ProductAssetAdministrationShell> ." in inserts
    assert "ProcessAssetAdministrationShell" not in inserts
    assert "ResourceAssetAdministrationShell" not in inserts


def test_projection_aas_production_planner_typed_as_resource():
    """productionPlannerAAS contains 'planner', not 'product' — must be ResourceAAS."""
    stmts = event_to_sparql(
        event=parse_event(
            {"type": "AAS_CREATED", "id": "urn:aas:resource:production-planner",
             "aas": {"id": "urn:aas:resource:production-planner",
                     "idShort": "productionPlannerAAS",
                     "assetInformation": {"assetKind": "Instance"}}},
            topic="aas-events"),
        base_uri="urn:kg:aas:", graph_iri=None, enable_projection=True)

    inserts = _insert_block(stmts)
    assert "ResourceAssetAdministrationShell" in inserts
    assert "ProductAssetAdministrationShell" not in inserts
    assert "ProcessAssetAdministrationShell" not in inserts


def test_projection_aas_deleted_cleans_shell_type_and_legacy_links():
    """AAS_DELETED removes the shell type and any legacy entity-link predicates."""
    event = parse_event(
        {"type": "AAS_DELETED", "id": "urn:aas:product:to-delete"},
        topic="aas-events",
    )
    joined = "\n".join(event_to_sparql(event=event, base_uri="urn:kg:aas:", graph_iri=None, enable_projection=True))

    # Shell types are cleaned up
    assert "AssetAdministrationShell" in joined  # type cleanup present
    # arso:hasResourceAAS is the canonical cleanup predicate; old names are absent.
    assert "hasResourceAAS" in joined
    assert "hasProductAAS" not in joined
    assert "hasProcessAAS" not in joined


# ---------------------------------------------------------------------------
# G2 / G8: Fixture-driven parametric tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fixture_path", sorted(FIXTURES.glob("*.json")), ids=lambda p: p.stem)
def test_fixture_event(fixture_path: pathlib.Path):
    """Each fixture JSON round-trips through event_to_sparql and produces the expected graph."""
    actual, expected = _load_fixture(fixture_path)
    assert to_isomorphic(actual) == to_isomorphic(expected), (
        f"Graph mismatch for {fixture_path.stem}.\n"
        f"Actual ({len(actual)} triples):\n{actual.serialize(format='turtle')}\n"
        f"Expected ({len(expected)} triples):\n{expected.serialize(format='turtle')}"
    )


# ---------------------------------------------------------------------------
# G3: Idempotency tests
# ---------------------------------------------------------------------------


def test_upsert_idempotent_sme():
    """Applying the same SME_CREATED event twice produces the same graph as once."""
    ev_dict = {
        "type": "SME_CREATED",
        "id": "urn:sm:idem",
        "smElementPath": "P1",
        "smElement": {"modelType": "Property", "idShort": "P1", "valueType": "xs:string", "value": "hello"},
    }
    g_once = _apply([(ev_dict, "submodel-events")])
    g_twice = _apply([(ev_dict, "submodel-events"), (ev_dict, "submodel-events")])

    assert to_isomorphic(g_once) == to_isomorphic(g_twice)


def test_upsert_replaces_old_value():
    """Applying SME_UPDATED with a new value overwrites the old property value."""
    base = {
        "type": "SME_CREATED",
        "id": "urn:sm:replace",
        "smElementPath": "P1",
        "smElement": {"modelType": "Property", "idShort": "P1", "valueType": "xs:string", "value": "old"},
    }
    update = dict(base, type="SME_UPDATED")
    update["smElement"] = dict(base["smElement"], value="new")

    g = _apply([(base, "submodel-events"), (update, "submodel-events")])

    AAS = rdflib.Namespace("https://admin-shell.io/aas/3/1/")
    sme_iri = rdflib.URIRef("urn:kg:aas:urn%3Asm%3Areplace%2Fsubmodel-elements%2FP1")
    values = list(g.objects(sme_iri, AAS["Property/value"]))
    assert values == [rdflib.Literal("new")], f"Expected ['new'], got {values}"


def test_upsert_idempotent_aas():
    """Applying AAS_CREATED twice results in the same 5-triple graph."""
    ev_dict = {
        "type": "AAS_CREATED",
        "id": "urn:aas:idem",
        "aas": {"id": "urn:aas:idem", "assetInformation": {"assetKind": "Instance"}},
    }
    g_once = _apply([(ev_dict, "aas-events")])
    g_twice = _apply([(ev_dict, "aas-events"), (ev_dict, "aas-events")])
    assert to_isomorphic(g_once) == to_isomorphic(g_twice)


# ---------------------------------------------------------------------------
# G4: Cascade boundary tests
# ---------------------------------------------------------------------------


def test_aas_deleted_leaves_submodel_intact():
    """Deleting an AAS removes its triples but does not touch a separately-created Submodel."""
    aas_ev = {
        "type": "AAS_CREATED",
        "id": "urn:aas:cascade",
        "aas": {"id": "urn:aas:cascade", "assetInformation": {"assetKind": "Instance"}},
    }
    sm_ev = {
        "type": "SM_CREATED",
        "id": "urn:sm:cascade",
        "submodel": {"id": "urn:sm:cascade", "submodelElements": []},
    }
    del_ev = {"type": "AAS_DELETED", "id": "urn:aas:cascade"}

    g = _apply([(aas_ev, "aas-events"), (sm_ev, "submodel-events"), (del_ev, "aas-events")])

    aas_iri = rdflib.URIRef("urn:kg:aas:urn%3Aaas%3Acascade")
    sm_iri = rdflib.URIRef("urn:kg:aas:urn%3Asm%3Acascade")

    assert len(list(g.triples((aas_iri, None, None)))) == 0, "AAS triples should be deleted"
    assert len(list(g.triples((sm_iri, None, None)))) > 0, "Submodel triples should survive"


def test_sm_deleted_cascades_named_children():
    """SM_DELETED removes the SM IRI's CBD (bnodes).
    Separately-inserted SME IRIs are NOT automatically removed — that is expected
    behaviour: the SM_DELETED event only deletes the SM's own triples. The caller
    must issue SME_DELETED events for each SME, or re-create the SM with a full
    submodelElements tree that links to the SME IRI via a named-child predicate."""
    sm_ev = {
        "type": "SM_CREATED",
        "id": "urn:sm:nested",
        "submodel": {"id": "urn:sm:nested", "submodelElements": []},
    }
    sme_ev = {
        "type": "SME_CREATED",
        "id": "urn:sm:nested",
        "smElementPath": "P1",
        "smElement": {"modelType": "Property", "idShort": "P1", "valueType": "xs:string", "value": "v"},
    }
    del_ev = {"type": "SM_DELETED", "id": "urn:sm:nested"}

    g = _apply([(sm_ev, "submodel-events"), (sme_ev, "submodel-events"), (del_ev, "submodel-events")])

    sm_iri = rdflib.URIRef("urn:kg:aas:urn%3Asm%3Anested")

    assert len(list(g.triples((sm_iri, None, None)))) == 0, "SM triples should be deleted"


def test_sm_ref_deleted_does_not_delete_submodel_node():
    """SM_REF_DELETED removes only the link triple, not the Submodel itself."""
    sm_ev = {
        "type": "SM_CREATED",
        "id": "urn:sm:link2",
        "submodel": {"id": "urn:sm:link2", "submodelElements": []},
    }
    link_ev = {"type": "SM_REF_ADDED", "id": "urn:aas:link2", "submodelId": "urn:sm:link2"}
    unlink_ev = {"type": "SM_REF_DELETED", "id": "urn:aas:link2", "submodelId": "urn:sm:link2"}

    g = _apply([(sm_ev, "submodel-events"), (link_ev, "aas-events"), (unlink_ev, "aas-events")])

    AAS = rdflib.Namespace("https://admin-shell.io/aas/3/1/")
    aas_iri = rdflib.URIRef("urn:kg:aas:urn%3Aaas%3Alink2")
    sm_iri = rdflib.URIRef("urn:kg:aas:urn%3Asm%3Alink2")

    assert (aas_iri, AAS["AssetAdministrationShell/submodels"], sm_iri) not in g, "Link should be removed"
    assert len(list(g.triples((sm_iri, None, None)))) > 0, "SM triples should survive"
