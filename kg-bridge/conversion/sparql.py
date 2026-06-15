from __future__ import annotations

from typing import Any

import rdflib
from rdflib.namespace import PROV, XSD

from .aas_models import AASNameSpace


_ANY_PREDICATE_SENTINEL = rdflib.URIRef("urn:py-aas-rdf:any-predicate")
_NAMED_CHILD_PREDICATES = (
    AASNameSpace.AAS["SubmodelElementCollection/value"],
    AASNameSpace.AAS["SubmodelElementList/value"],
    AASNameSpace.AAS["Entity/statements"],
)


def _indent(text: str, prefix: str) -> str:
    return "\n".join(f"{prefix}{line}" if line else prefix for line in text.splitlines())


def _wrap_graph_pattern(pattern: str, graph_iri: str | None, indent: str = "  ") -> str:
    if graph_iri:
        return f"{indent}GRAPH <{graph_iri}> {{\n{_indent(pattern, indent + '  ')}\n{indent}}}"
    return _indent(pattern, indent)


def _replace_term(graph: rdflib.Graph, old_term: rdflib.term.Node, new_term: rdflib.term.Node) -> rdflib.Graph:
    replaced = rdflib.Graph()
    for subject, predicate, obj in graph:
        next_subject = new_term if subject == old_term else subject
        next_obj = new_term if obj == old_term else obj
        replaced.add((next_subject, predicate, next_obj))
    return replaced


def _serialize_nt(graph: rdflib.Graph) -> str:
    serialized = graph.serialize(format="nt")
    if isinstance(serialized, bytes):
        serialized = serialized.decode("utf-8")
    return serialized.strip()


def _delete_scope_pattern(target_iri: rdflib.URIRef, cascade_named_children: bool) -> str:
    any_predicate = _ANY_PREDICATE_SENTINEL.n3()
    target = target_iri.n3()

    base_scope = (
        "{\n"
        f"  {target} ({any_predicate}|!{any_predicate})* ?s .\n"
        f"  FILTER(?s = {target} || isBlank(?s))\n"
        "}"
    )

    if not cascade_named_children:
        return f"{base_scope}\n?s ?p ?o ."

    child_path = " | ".join(predicate.n3() for predicate in _NAMED_CHILD_PREDICATES)
    named_scope = (
        "{\n"
        f"  {target} ({child_path})+ ?s .\n"
        "  FILTER(isIRI(?s))\n"
        "}"
    )

    return f"{base_scope}\nUNION\n{named_scope}\n?s ?p ?o ."


def _append_provenance(graph: rdflib.Graph, subject: rdflib.URIRef, provenance: dict[str, Any] | None) -> None:
    if not provenance:
        return

    source_url = provenance.get("sourceUrl")
    if isinstance(source_url, str) and source_url:
        if source_url.startswith(("http://", "https://", "urn:")):
            graph.add((subject, PROV.wasDerivedFrom, rdflib.URIRef(source_url)))
        else:
            graph.add((subject, PROV.wasDerivedFrom, rdflib.Literal(source_url)))

    registration_time = provenance.get("registrationTime")
    if registration_time is not None:
        if isinstance(registration_time, (int, float)):
            graph.add((subject, PROV.generatedAtTime, rdflib.Literal(int(registration_time), datatype=XSD.long)))
        else:
            graph.add((subject, PROV.generatedAtTime, rdflib.Literal(str(registration_time))))


def build_upsert(
    model: Any,
    target_iri: rdflib.URIRef | None = None,
    graph_iri: str | None = None,
    base_uri: str = "",
    id_strategy: str = "url-encode",
    cascade_named_children: bool = True,
    provenance: dict[str, Any] | None = None,
    to_rdf_kwargs: dict[str, Any] | None = None,
) -> str:
    rdf_kwargs = {
        "base_uri": base_uri,
        "id_strategy": id_strategy,
    }
    if to_rdf_kwargs:
        rdf_kwargs.update(to_rdf_kwargs)

    graph, model_subject = model.to_rdf(**rdf_kwargs)
    model_subject_ref = model_subject if isinstance(model_subject, rdflib.URIRef) else None

    if target_iri is not None and model_subject_ref is not None and model_subject_ref != target_iri:
        graph = _replace_term(graph, model_subject_ref, target_iri)
        model_subject_ref = target_iri

    if target_iri is None:
        if model_subject_ref is None:
            raise ValueError("build_upsert requires a URIRef target_iri for blank-node roots")
        target_iri = model_subject_ref

    _append_provenance(graph, target_iri, provenance)

    delete_scope = _delete_scope_pattern(target_iri, cascade_named_children=cascade_named_children)
    insert_payload = _serialize_nt(graph)

    delete_block = "DELETE {\n" + _wrap_graph_pattern("?s ?p ?o .", graph_iri) + "\n}"
    where_block = "WHERE {\n" + _wrap_graph_pattern(delete_scope, graph_iri) + "\n}"
    delete_stmt = "\n".join([delete_block, where_block])

    insert_block = "INSERT DATA {\n" + _wrap_graph_pattern(insert_payload, graph_iri) + "\n}"

    return "\n;\n".join([delete_stmt, insert_block])


def build_delete(
    target_iri: rdflib.URIRef,
    graph_iri: str | None = None,
    cascade_named_children: bool = True,
) -> str:
    delete_scope = _delete_scope_pattern(target_iri, cascade_named_children=cascade_named_children)

    delete_block = "DELETE {\n" + _wrap_graph_pattern("?s ?p ?o .", graph_iri) + "\n}"
    where_block = "WHERE {\n" + _wrap_graph_pattern(delete_scope, graph_iri) + "\n}"
    return "\n".join([delete_block, where_block])


def build_link(
    parent_iri: rdflib.URIRef,
    predicate_iri: rdflib.URIRef,
    child_iri: rdflib.URIRef,
    graph_iri: str | None = None,
) -> str:
    triple = f"{parent_iri.n3()} {predicate_iri.n3()} {child_iri.n3()} ."
    body = _wrap_graph_pattern(triple, graph_iri)
    return f"INSERT DATA {{\n{body}\n}}"


def build_unlink(
    parent_iri: rdflib.URIRef,
    predicate_iri: rdflib.URIRef,
    child_iri: rdflib.URIRef,
    graph_iri: str | None = None,
) -> str:
    triple = f"{parent_iri.n3()} {predicate_iri.n3()} {child_iri.n3()} ."
    body = _wrap_graph_pattern(triple, graph_iri)
    return f"DELETE WHERE {{\n{body}\n}}"
