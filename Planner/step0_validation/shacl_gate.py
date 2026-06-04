from __future__ import annotations

import logging
from dataclasses import dataclass

import requests
from rdflib import Graph

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ShaclGateConfig:
    """Configuration for pre-planning SHACL validation against Fuseki graphs."""

    enabled: bool = False
    sparql_endpoint: str = "http://kg-fuseki:3030/kg/sparql"
    abox_graph_iri: str = "urn:kg:abox"
    tbox_graph_iri: str = "urn:kg:tbox"
    shacl_graph_iri: str = "urn:kg:shacl"
    timeout_seconds: float = 20.0
    inference: str = "rdfs"


@dataclass(frozen=True)
class ShaclGateResult:
    """Result payload for pre-planning SHACL gate execution."""

    executed: bool
    conforms: bool
    report_text: str
    data_triples: int
    shape_triples: int


def _load_pyshacl_validate():
    try:
        from pyshacl import validate
    except ImportError as exc:
        raise RuntimeError("pyshacl is required when PLANNER_SHACL_GATE_ENABLED=true") from exc
    return validate


def _query_all_graph(graph_iri: str) -> str:
    return f"""
CONSTRUCT {{ ?s ?p ?o . }}
FROM <{graph_iri}>
WHERE {{ ?s ?p ?o . }}
""".strip()


def _query_structural_abox(abox_graph_iri: str) -> str:
    return f"""
PREFIX apex: <https://w3id.org/2026/apex/>
CONSTRUCT {{ ?s ?p ?o . }}
FROM <{abox_graph_iri}>
WHERE {{
  ?s ?p ?o .
  FILTER(?p != apex:smElementValue)
}}
""".strip()


def _fetch_graph(sparql_endpoint: str, query: str, timeout_seconds: float) -> Graph:
    response = requests.post(
        sparql_endpoint,
        data={"query": query},
        headers={"Accept": "text/turtle"},
        timeout=timeout_seconds,
    )
    response.raise_for_status()

    graph = Graph()
    payload = response.text.strip()
    if payload:
        graph.parse(data=payload, format="turtle")
    return graph


def run_pre_planning_shacl_gate(config: ShaclGateConfig) -> ShaclGateResult:
    """Validate structural KG state before planning and fail fast on SHACL errors."""

    if not config.enabled:
        return ShaclGateResult(
            executed=False,
            conforms=True,
            report_text="SHACL pre-planning gate disabled.",
            data_triples=0,
            shape_triples=0,
        )

    logger.info("Running SHACL pre-planning gate via %s", config.sparql_endpoint)

    data_graph = _fetch_graph(
        config.sparql_endpoint,
        _query_structural_abox(config.abox_graph_iri),
        config.timeout_seconds,
    )
    tbox_graph = _fetch_graph(
        config.sparql_endpoint,
        _query_all_graph(config.tbox_graph_iri),
        config.timeout_seconds,
    )
    shacl_graph = _fetch_graph(
        config.sparql_endpoint,
        _query_all_graph(config.shacl_graph_iri),
        config.timeout_seconds,
    )

    if len(shacl_graph) == 0:
        raise RuntimeError(
            f"SHACL graph {config.shacl_graph_iri} is empty; aborting as fail-fast gate policy"
        )

    merged_data = Graph()
    merged_data += data_graph
    merged_data += tbox_graph

    validate = _load_pyshacl_validate()
    conforms, _report_graph, report_text = validate(
        data_graph=merged_data,
        shacl_graph=shacl_graph,
        ont_graph=tbox_graph,
        inference=config.inference,
        advanced=True,
        meta_shacl=False,
        debug=False,
    )

    return ShaclGateResult(
        executed=True,
        conforms=bool(conforms),
        report_text=str(report_text),
        data_triples=len(merged_data),
        shape_triples=len(shacl_graph),
    )
