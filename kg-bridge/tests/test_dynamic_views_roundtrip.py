from __future__ import annotations

from pathlib import Path
import re

import rdflib

from conversion import aas_iri, event_to_sparql, parse_event, submodel_element_iri, submodel_iri


BASE_URI = "urn:kg:aas:"
ABOX_GRAPH = rdflib.URIRef("urn:kg:abox")
TBOX_GRAPH = rdflib.URIRef("urn:kg:tbox")

AAS = rdflib.Namespace("https://admin-shell.io/aas/3/1/")
ARSO = rdflib.Namespace("https://w3id.org/2025/arso#")
APEX = rdflib.Namespace("https://w3id.org/2026/apex/")
CSS = rdflib.Namespace("http://www.w3id.org/hsu-aut/css#")
RDF = rdflib.RDF


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _view_query(name: str) -> str:
    query = (_repo_root() / "kg-bridge" / "sparql" / "views" / name).read_text(encoding="utf-8")
    query = query.replace(
        "aas:Submodel/submodelElements",
        "<https://admin-shell.io/aas/3/1/Submodel/submodelElements>",
    )
    query = query.replace("FROM <urn:kg:tbox>\n", "")
    query = query.replace("FROM <urn:kg:abox>\n", "")
    query = re.sub(r"^\s*BIND\(IRI\(CONCAT\(\"urn:kg:apex:[^\n]*AS \?fact\)\s*$", "  BIND(BNODE() AS ?fact)", query, flags=re.MULTILINE)
    query = query.replace('  BIND(IRI(CONCAT(STR(?fact), ":arg1")) AS ?arg1)', '  BIND(BNODE() AS ?arg1)')
    query = query.replace('  BIND(IRI(CONCAT(STR(?fact), ":arg2")) AS ?arg2)', '  BIND(BNODE() AS ?arg2)')
    return query


def _run_construct(graph: rdflib.Graph, view_name: str) -> rdflib.Graph:
    return graph.query(_view_query(view_name)).graph


def _normalize_update_for_rdflib(update: str) -> str:
    stripped = update.strip()
    if stripped.upper().startswith("DELETE WHERE"):
        return ""
    return update


def _apply_event(graph: rdflib.Graph, payload: dict, topic: str) -> None:
    event = parse_event(payload, topic=topic)
    statements = event_to_sparql(
        event=event,
        base_uri=BASE_URI,
        graph_iri=None,
        enable_projection=True,
    )
    for statement in statements:
        normalized = _normalize_update_for_rdflib(statement)
        if not normalized.strip():
            continue
        graph.update(normalized)


def _upsert_mirrored_projection(
    graph: rdflib.Graph,
    sm_id: str,
    path: str,
    id_short: str,
    value: str | bool,
) -> None:
    if path.endswith(id_short):
        canonical_path = path
    else:
        canonical_path = f"{path}.{id_short}" if path else id_short

    sme = submodel_element_iri(BASE_URI, sm_id, canonical_path)
    sm = submodel_iri(BASE_URI, sm_id)
    value_n3 = rdflib.Literal(value).n3()
    path_n3 = rdflib.Literal(canonical_path).n3()

    graph.update(
        "\n".join(
            [
                "PREFIX apex: <https://w3id.org/2026/apex/>",
                "DELETE {",
                f"  {sme.n3()} apex:smElementPath ?old_path .",
                f"  {sme.n3()} apex:smElementModelType ?old_type .",
                f"  {sme.n3()} apex:smElementValue ?old_value .",
                "}",
                "INSERT {",
                f"  {sm.n3()} <https://admin-shell.io/aas/3/1/Submodel/submodelElements> {sme.n3()} .",
                f"  {sme.n3()} a apex:MirroredSubmodelElement .",
                f"  {sme.n3()} apex:smElementPath {path_n3} .",
                f"  {sme.n3()} apex:smElementModelType \"Property\" .",
                f"  {sme.n3()} apex:smElementValue {value_n3} .",
                "}",
                "WHERE {",
                f"  OPTIONAL {{ {sme.n3()} apex:smElementPath ?old_path . }}",
                f"  OPTIONAL {{ {sme.n3()} apex:smElementModelType ?old_type . }}",
                f"  OPTIONAL {{ {sme.n3()} apex:smElementValue ?old_value . }}",
                "}",
            ]
        )
    )


def _insert_operational_submodel_link(graph: rdflib.Graph, aas_id: str, sm_id: str) -> None:
    aas_node = aas_iri(BASE_URI, aas_id)
    sm_node = submodel_iri(BASE_URI, sm_id)
    graph.update(
        "\n".join(
            [
                "PREFIX arso: <https://w3id.org/2025/arso#>",
                "INSERT DATA {",
                f"  {aas_node.n3()} arso:hasOperationalDataSubmodel {sm_node.n3()} .",
                "}",
            ]
        )
    )


def _create_actor(graph: rdflib.Graph, aas_id: str, sm_id: str, id_short: str) -> None:
    _apply_event(
        graph,
        {
            "type": "AAS_CREATED",
            "id": aas_id,
            "aas": {
                "id": aas_id,
                "idShort": id_short,
                "assetInformation": {"assetKind": "Instance"},
            },
        },
        topic="aas-events",
    )
    _apply_event(
        graph,
        {
            "type": "SM_CREATED",
            "id": sm_id,
            "submodel": {
                "id": sm_id,
                "submodelElements": [],
            },
        },
        topic="submodel-events",
    )
    _apply_event(
        graph,
        {
            "type": "SM_REF_ADDED",
            "id": aas_id,
            "submodelId": sm_id,
        },
        topic="aas-events",
    )
    _insert_operational_submodel_link(graph, aas_id=aas_id, sm_id=sm_id)


def _emit_sme(graph: rdflib.Graph, sm_id: str, path: str, id_short: str, value: str | bool, event_type: str) -> None:
    _apply_event(
        graph,
        {
            "type": event_type,
            "id": sm_id,
            "smElementPath": path,
            "smElement": {
                "modelType": "Property",
                "idShort": id_short,
                "valueType": "xs:string" if isinstance(value, str) else "xs:boolean",
                "value": value,
            },
        },
        topic="submodel-events",
    )
    _upsert_mirrored_projection(graph, sm_id=sm_id, path=path, id_short=id_short, value=value)


def _argument_literal_for_entity(facts: rdflib.Graph, predicate_class: rdflib.URIRef, entity: rdflib.URIRef) -> set[rdflib.Literal]:
    values: set[rdflib.Literal] = set()
    for fact in facts.subjects(RDF.type, predicate_class):
        for arg in facts.objects(fact, APEX["hasArgumentBinding"]):
            if facts.value(arg, APEX["argumentIndex"]) != rdflib.Literal(1):
                continue
            if facts.value(arg, APEX["argumentObject"]) != entity:
                continue
            for arg2 in facts.objects(fact, APEX["hasArgumentBinding"]):
                if facts.value(arg2, APEX["argumentIndex"]) == rdflib.Literal(2):
                    literal = facts.value(arg2, APEX["argumentLiteral"])
                    if isinstance(literal, rdflib.Literal):
                        values.add(literal)
    return values


def _entity_bound_as_first_argument(
    facts: rdflib.Graph,
    predicate_class: rdflib.URIRef,
    expected_fragment: str,
) -> rdflib.URIRef:
    for fact in facts.subjects(RDF.type, predicate_class):
        for arg in facts.objects(fact, APEX["hasArgumentBinding"]):
            if facts.value(arg, APEX["argumentIndex"]) != rdflib.Literal(1):
                continue
            obj = facts.value(arg, APEX["argumentObject"])
            if isinstance(obj, rdflib.URIRef) and expected_fragment in str(obj):
                return obj
    raise AssertionError(f"No predicate argument matched fragment: {expected_fragment}")


def test_deployment_seed_is_present_and_query_ready():
    seed_file = _repo_root() / "kg-bridge" / "Ontology" / "deployment" / "aau_filling_line_seed.ttl"
    graph = rdflib.Graph()
    graph.parse(seed_file, format="turtle")

    assert (None, RDF.type, CSS["Resource"]) in graph
    assert (None, RDF.type, CSS["Product"]) in graph
    assert (None, ARSO["hasOperationalDataSubmodel"], None) in graph
    assert (None, APEX["smElementValue"], None) in graph


def test_dynamic_views_react_immediately_to_sme_updates():
    dataset = rdflib.Graph()

    resource_aas = "urn:aas:resource:carrier-01"
    resource_sm = "urn:sm:resource:carrier-01:operational-data"
    station_aas = "urn:aas:resource:station-loading-01"
    station_sm = "urn:sm:resource:station-loading-01:operational-data"
    product_aas = "urn:aas:product:batch-01"
    product_sm = "urn:sm:product:batch-01:operational-data"

    _create_actor(dataset, aas_id=resource_aas, sm_id=resource_sm, id_short="CarrierResourceAAS")
    _create_actor(dataset, aas_id=station_aas, sm_id=station_sm, id_short="LoadingStationAAS")
    _create_actor(dataset, aas_id=product_aas, sm_id=product_sm, id_short="ProductBatchAAS")

    _emit_sme(dataset, resource_sm, "Runtime.CurrentLocation", "CurrentLocation", "loading-cell-01", "SME_CREATED")
    _emit_sme(dataset, resource_sm, "Runtime.PositionX", "PositionX", "0.0", "SME_CREATED")
    _emit_sme(dataset, resource_sm, "Runtime.PositionY", "PositionY", "0.0", "SME_CREATED")
    _emit_sme(dataset, resource_sm, "Runtime.IsOccupied", "IsOccupied", "true", "SME_CREATED")
    _emit_sme(dataset, resource_sm, "Runtime.OperationalStatus", "OperationalStatus", "true", "SME_CREATED")
    _emit_sme(dataset, station_sm, "Runtime.StationLocation", "StationLocation", "loading-cell-01", "SME_CREATED")
    _emit_sme(dataset, station_sm, "Runtime.PositionX", "PositionX", "0.0", "SME_CREATED")
    _emit_sme(dataset, station_sm, "Runtime.PositionY", "PositionY", "0.5", "SME_CREATED")
    _emit_sme(dataset, station_sm, "Runtime.OperationalStatus", "OperationalStatus", "true", "SME_CREATED")
    _emit_sme(dataset, product_sm, "Runtime.CurrentLocation", "CurrentLocation", "loading-cell-01", "SME_CREATED")

    resource_at = _run_construct(dataset, "resource-at.rq")
    product_at = _run_construct(dataset, "product-at.rq")
    occupied = _run_construct(dataset, "occupied.rq")
    operational = _run_construct(dataset, "operational.rq")
    in_range = _run_construct(dataset, "in-range.rq")

    assert (None, RDF.type, APEX["ResourceAt"]) in resource_at
    assert (None, RDF.type, APEX["ProductAt"]) in product_at
    assert (None, RDF.type, APEX["Occupied"]) in occupied
    assert (None, RDF.type, APEX["Operational"]) in operational
    assert (None, RDF.type, APEX["InRange"]) in in_range

    resource_entity = _entity_bound_as_first_argument(resource_at, APEX["ResourceAt"], "carrier-01")
    assert rdflib.Literal("loading-cell-01") in _argument_literal_for_entity(resource_at, APEX["ResourceAt"], resource_entity)

    _emit_sme(dataset, resource_sm, "Runtime.CurrentLocation", "CurrentLocation", "inspection-cell-02", "SME_UPDATED")
    _emit_sme(dataset, resource_sm, "Runtime.PositionX", "PositionX", "5.0", "SME_UPDATED")
    _emit_sme(dataset, resource_sm, "Runtime.PositionY", "PositionY", "5.0", "SME_UPDATED")

    resource_at_after_move = _run_construct(dataset, "resource-at.rq")
    in_range_after_move = _run_construct(dataset, "in-range.rq")

    values_after_move = _argument_literal_for_entity(resource_at_after_move, APEX["ResourceAt"], resource_entity)
    assert rdflib.Literal("inspection-cell-02") in values_after_move
    assert rdflib.Literal("loading-cell-01") not in values_after_move
    assert (None, RDF.type, APEX["InRange"]) not in in_range_after_move

    _emit_sme(dataset, station_sm, "Runtime.StationLocation", "StationLocation", "inspection-cell-02", "SME_UPDATED")
    _emit_sme(dataset, station_sm, "Runtime.PositionX", "PositionX", "5.0", "SME_UPDATED")
    _emit_sme(dataset, station_sm, "Runtime.PositionY", "PositionY", "5.0", "SME_UPDATED")

    in_range_after_station_update = _run_construct(dataset, "in-range.rq")
    assert (None, RDF.type, APEX["InRange"]) in in_range_after_station_update