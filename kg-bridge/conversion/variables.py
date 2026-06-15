"""Semantic-ID-driven projection of Variables/OperationalData submodel elements
into runtime predicate observations.

For each variable element in an OperationalData/Variables submodel, the projector
emits a typed predicate-observation node with a back-link to the owning submodel.
The view queries (operational.rq, occupied.rq, etc.) join across the
``arso:hasOperationalDataSubmodel`` / ``apex:projectedFromSubmodel`` edges to
materialize the full predicate instances (``apex:Operational(Resource)`` etc.)
with argument bindings.

This replaces the former approach of mirroring elements into
``apex:MirroredSubmodelElement`` nodes and navigating via ``apex:hasMirroredElement``.
"""

from __future__ import annotations

import hashlib
from typing import Any

import rdflib

from .sparql import build_unlink

APEX = rdflib.Namespace("https://w3id.org/2026/apex/")
RDF = rdflib.RDF

# Semantic ID → predicate class mapping for known variables.
# Semantic IDs whose observations directly represent a predicate fact get the
# predicate type stamped on the observation node. Position/coordinate semantic IDs
# are auxiliary data used by the in-range view to compute relative distance;
# their observations carry only apex:PredicateObservation (no specific predicate type).
_SEMANTIC_ID_TO_PREDICATE: dict[str, rdflib.URIRef | None] = {
    "https://w3id.org/2026/apex/semantic/state/operational": APEX["Operational"],
    "https://w3id.org/2026/apex/semantic/state/occupied": APEX["Occupied"],
    "https://w3id.org/2026/apex/semantic/location/label": APEX["ResourceAt"],
    # Position coordinates — auxiliary data, no specific predicate type.
    "https://w3id.org/2026/apex/semantic/position/x": None,
    "https://w3id.org/2026/apex/semantic/position/y": None,
    "https://w3id.org/2026/apex/semantic/position/z": None,
    "https://w3id.org/2026/apex/semantic/position/yaw": None,
}


def _own_semantic_id(model: Any) -> str | None:
    """First key value of the element's primary semanticId, or None."""
    ref = getattr(model, "semanticId", None)
    keys = getattr(ref, "keys", None) if ref is not None else None
    if not isinstance(keys, list):
        return None
    for key in keys:
        value = getattr(key, "value", None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _fact_iri(submodel_node_iri: str, semantic_id: str, path: str) -> rdflib.URIRef:
    """Deterministic IRI for a predicate-observation node.

    Matches the shape the view CONSTRUCT queries expect
    (``urn:kg:apex:{predicateLower}:{sha256(summary)}``).
    """
    raw = f"{submodel_node_iri}|{semantic_id}|{path}"
    return rdflib.URIRef(
        "urn:kg:apex:predicate-observation:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()
    )


def _insert_data(lines: list[str], graph_iri: str | None) -> str:
    if not lines:
        return ""
    if graph_iri:
        body = "\n".join(f"    {line}" for line in lines)
        return f"INSERT DATA {{\n  GRAPH <{graph_iri}> {{\n{body}\n  }}\n}}"
    body = "\n".join(f"  {line}" for line in lines)
    return f"INSERT DATA {{\n{body}\n}}"


# ── Projector ───────────────────────────────────────────────────

def variables_observation_statements(
    submodel_node: rdflib.URIRef,
    element: Any,
    path: str | None,
    graph_iri: str | None,
    *,
    is_delete: bool = False,
) -> list[str]:
    """Project a runtime predicate observation for a single variable element.

    Returns SPARQL UPDATE statements (INSERT DATA or DELETE + INSERT for updates),
    or [] if the element is not a recognised variable.

    When *is_delete* is True, only a DELETE statement for the prior observation is
    emitted (no replacement INSERT).
    """
    semantic_id = _own_semantic_id(element)
    if not semantic_id or semantic_id not in _SEMANTIC_ID_TO_PREDICATE:
        return []

    predicate_type = _SEMANTIC_ID_TO_PREDICATE[semantic_id]
    value = getattr(element, "value", None)
    if not isinstance(value, (str, int, float, bool)):
        return []

    submodel_str = str(submodel_node)
    path_str = (path or "").strip()
    fact_node = _fact_iri(submodel_str, semantic_id, path_str)

    sm_n3 = submodel_node.n3()
    fact_n3 = fact_node.n3()
    statements: list[str] = []

    # Remove prior observation for this (submodel, semanticId, path) tuple.
    statements.append(
        _delete_prior_observation(fact_n3, graph_iri)
    )

    if is_delete:
        return [s for s in statements if s]

    # Insert new observation.
    insert_lines = [
        f"{fact_n3} a {APEX['PredicateObservation'].n3()} .",
        f"{fact_n3} {APEX['projectedFromSubmodel'].n3()} {sm_n3} .",
        f"{fact_n3} {APEX['predicateSemanticId'].n3()} {rdflib.Literal(semantic_id).n3()} .",
        f"{fact_n3} {APEX['predicateValue'].n3()} {rdflib.Literal(value).n3()} .",
    ]
    if predicate_type is not None:
        # Stamp the specific predicate type when the semantic ID maps directly
        # to a predicate class. Position/coordinate observations get no predicate type.
        insert_lines.insert(1, f"{fact_n3} a {predicate_type.n3()} .")
    statements.append(_insert_data(insert_lines, graph_iri))

    return [s for s in statements if s]


def variables_observations_for_submodel(
    submodel_node: rdflib.URIRef,
    submodel: Any,
    graph_iri: str | None,
    *,
    is_update: bool = False,
) -> list[str]:
    """Walk a submodel's top-level elements and project all recognised variable observations.

    Called on SM_CREATED/UPDATED. On update, the prior observations were already deleted
    by ``_delete_submodel_observations()`` so each element's INSERT is clean.
    """
    statements: list[str] = []
    elements = getattr(submodel, "submodelElements", None)
    if not isinstance(elements, list):
        return statements

    for element in elements:
        id_short = getattr(element, "idShort", None)
        if not id_short:
            continue
        statements.extend(
            variables_observation_statements(
                submodel_node=submodel_node,
                element=element,
                path=id_short,
                graph_iri=graph_iri,
            )
        )
    return statements


def delete_submodel_observations(
    submodel_node: rdflib.URIRef,
    graph_iri: str | None,
) -> str:
    """Remove all ``apex:PredicateObservation`` nodes projected from this submodel
    (cascade delete for SM_UPDATED/SM_DELETED re-projection)."""
    pf = APEX["projectedFromSubmodel"].n3()
    po = APEX["PredicateObservation"]

    if graph_iri:
        return (
            "DELETE {\n"
            f"  GRAPH <{graph_iri}> {{\n"
            f"    ?obs ?p ?o .\n"
            "  }\n"
            "}\n"
            "WHERE {\n"
            f"  GRAPH <{graph_iri}> {{\n"
            f"    ?obs ?p ?o .\n"
            f"    ?obs a {po.n3()} .\n"
            f"    ?obs {pf} {submodel_node.n3()} .\n"
            "  }\n"
            "}"
        )
    return (
        "DELETE {\n"
        "  ?obs ?p ?o .\n"
        "}\n"
        "WHERE {\n"
        f"  ?obs ?p ?o .\n"
        f"  ?obs a {po.n3()} .\n"
        f"  ?obs {pf} {submodel_node.n3()} .\n"
        "}"
    )


def _delete_prior_observation(
    fact_n3: str,
    graph_iri: str | None,
) -> str:
    """Delete any existing triples for the given fact IRI (idempotent re-projection)."""
    if graph_iri:
        return (
            "DELETE {\n"
            f"  GRAPH <{graph_iri}> {{\n"
            f"    {fact_n3} ?p ?o .\n"
            "  }\n"
            "}\n"
            "WHERE {\n"
            f"  GRAPH <{graph_iri}> {{\n"
            f"    {fact_n3} ?p ?o .\n"
            "  }\n"
            "}"
        )
    return (
        "DELETE WHERE {\n"
        f"  {fact_n3} ?p ?o .\n"
        "}"
    )
