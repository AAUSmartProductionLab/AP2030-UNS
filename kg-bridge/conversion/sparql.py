from __future__ import annotations

from typing import Any

import rdflib

from .aas_models import AASNameSpace


_ANY_PREDICATE_SENTINEL = rdflib.URIRef("urn:py-aas-rdf:any-predicate")


def _indent(text: str, prefix: str) -> str:
    return "\n".join(f"{prefix}{line}" if line else prefix for line in text.splitlines())


def _wrap_graph_pattern(pattern: str, graph_iri: str | None, indent: str = "  ") -> str:
    if graph_iri:
        return f"{indent}GRAPH <{graph_iri}> {{\n{_indent(pattern, indent + '  ')}\n{indent}}}"
    return _indent(pattern, indent)


def _delete_scope_pattern(target_iri: rdflib.URIRef, cascade_named_children: bool) -> str:
    any_predicate = _ANY_PREDICATE_SENTINEL.n3()
    target = target_iri.n3()

    base_scope = (
        "{\n"
        f"  {target} ({any_predicate}|!{any_predicate})* ?s .\n"
        f"  FILTER(?s = {target} || isBlank(?s))\n"
        "}"
    )

    # cascade_named_children was used by the legacy build_upsert full-mirror path
    # to cascade-delete named submodel-element children. The compact projection
    # layer now handles deletion via explicit DELETE statements in projection.py,
    # so cascade is no longer needed — always delete only blank-node subtrees.
    return f"{base_scope}\n?s ?p ?o ."


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
