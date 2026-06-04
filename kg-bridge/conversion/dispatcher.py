from __future__ import annotations

from typing import Any

import rdflib

from .events import AasEvent, AasEventType, SubmodelEvent, SubmodelEventType
from .iri import aas_iri, submodel_element_iri, submodel_iri
from .projection import projection_statements_for_event
from .sparql import build_delete, build_link, build_unlink, build_upsert
from py_aas_rdf.models.aas_namespace import AASNameSpace

_ANY_PREDICATE_SENTINEL = rdflib.URIRef("urn:py-aas-rdf:any-predicate")


def _canonical_path(path: str | None) -> str:
    normalized = (path or "").strip().replace("/", ".")
    tokens = [token for token in normalized.split(".") if token]
    return ".".join(tokens)


def _path_last_token(path: str) -> str | None:
    if not path:
        return None
    return path.split(".")[-1]


def _ensure_path_has_id_short(path: str | None, id_short: str | None) -> str:
    canonical = _canonical_path(path)
    if not id_short:
        return canonical

    last = _path_last_token(canonical)
    if last == id_short:
        return canonical

    if not canonical:
        return id_short

    if last and last.endswith("]"):
        return f"{canonical}.{id_short}"

    return canonical


def _encode_list_indices(path: str) -> str:
    segments = []
    for token in path.split("."):
        if not token:
            continue
        open_bracket = token.find("[")
        close_bracket = token.find("]", open_bracket + 1)
        if open_bracket > 0 and close_bracket > open_bracket:
            head = token[:open_bracket]
            index = token[open_bracket + 1 : close_bracket]
            segments.append(f"{head}%5B{index}%5D")
        else:
            segments.append(token)
    return ".".join(segments)


def _sme_to_rdf_kwargs(submodel_id: str, sm_element_path: str, id_strategy: str) -> dict[str, Any]:
    if id_strategy == "base64-url-encode":
        from py_aas_rdf.models import base_64_url_encode

        base_prefix = f"{base_64_url_encode(submodel_id)}/submodel-elements/"
    elif id_strategy == "identity":
        # Mirror py_aas_rdf submodel.to_rdf identity common_pref exactly.
        base_prefix = f"{submodel_id}/submodel-elements/"
    else:
        from py_aas_rdf.models import url_encode

        base_prefix = url_encode(f"{submodel_id}/submodel-elements/")

    parent_path = ""
    if "." in sm_element_path:
        parent_path = sm_element_path.rsplit(".", 1)[0]

    parent_prefix = _encode_list_indices(parent_path)
    prefix_uri = f"{base_prefix}{parent_prefix}." if parent_prefix else base_prefix

    return {
        "prefix_uri": prefix_uri,
        "id_strategy": id_strategy,
    }


def _submodel_id_from_reference(event: AasEvent) -> str | None:
    if event.submodelId:
        return event.submodelId

    if event.reference and event.reference.keys:
        first_key = event.reference.keys[0]
        if first_key.value:
            return first_key.value

    return None


def _asset_information_set_statement(
    event: AasEvent,
    base_uri: str,
    graph_iri: str | None,
    id_strategy: str,
    provenance: dict[str, Any] | None,
) -> str:
    if event.assetInformation is None:
        raise ValueError("ASSET_INFORMATION_SET requires assetInformation")

    target_aas = aas_iri(base_uri, event.id, id_strategy=id_strategy)
    asset_information_predicate = AASNameSpace.AAS["AssetAdministrationShell/assetInformation"]

    graph = rdflib.Graph()
    _, asset_info_node = event.assetInformation.to_rdf(graph=graph, base_uri=base_uri, id_strategy=id_strategy)

    if provenance:
        source_url = provenance.get("sourceUrl")
        if isinstance(source_url, str) and source_url:
            if source_url.startswith(("http://", "https://", "urn:")):
                graph.add((target_aas, rdflib.namespace.PROV.wasDerivedFrom, rdflib.URIRef(source_url)))
            else:
                graph.add((target_aas, rdflib.namespace.PROV.wasDerivedFrom, rdflib.Literal(source_url)))

        registration_time = provenance.get("registrationTime")
        if registration_time is not None:
            if isinstance(registration_time, (int, float)):
                graph.add(
                    (
                        target_aas,
                        rdflib.namespace.PROV.generatedAtTime,
                        rdflib.Literal(int(registration_time), datatype=rdflib.namespace.XSD.long),
                    )
                )
            else:
                graph.add(
                    (
                        target_aas,
                        rdflib.namespace.PROV.generatedAtTime,
                        rdflib.Literal(str(registration_time)),
                    )
                )

    serialized = graph.serialize(format="nt")
    if isinstance(serialized, bytes):
        serialized = serialized.decode("utf-8")
    insert_payload = (
        f"{target_aas.n3()} {asset_information_predicate.n3()} {asset_info_node.n3()} .\n{serialized.strip()}".strip()
    )

    any_predicate = _ANY_PREDICATE_SENTINEL.n3()
    delete_scope = (
        f"{target_aas.n3()} {asset_information_predicate.n3()} ?old_asset_info .\n"
        f"OPTIONAL {{\n"
        f"  ?old_asset_info ({any_predicate}|!{any_predicate})* ?s .\n"
        f"  FILTER(?s = ?old_asset_info || isBlank(?s))\n"
        f"  ?s ?p ?o .\n"
        f"}}"
    )

    if graph_iri:
        delete_block = (
            "DELETE {\n"
            f"  GRAPH <{graph_iri}> {{\n"
            f"    {target_aas.n3()} {asset_information_predicate.n3()} ?old_asset_info .\n"
            "    ?s ?p ?o .\n"
            "  }\n"
            "}"
        )
        where_block = (
            "WHERE {\n"
            f"  GRAPH <{graph_iri}> {{\n"
            + "\n".join(f"    {line}" for line in delete_scope.splitlines())
            + "\n"
            "  }\n"
            "}"
        )
        insert_block = (
            "INSERT DATA {\n"
            f"  GRAPH <{graph_iri}> {{\n"
            + "\n".join(f"    {line}" for line in insert_payload.splitlines())
            + "\n"
            "  }\n"
            "}"
        )
    else:
        delete_block = (
            "DELETE {\n"
            f"  {target_aas.n3()} {asset_information_predicate.n3()} ?old_asset_info .\n"
            "  ?s ?p ?o .\n"
            "}"
        )
        where_block = "WHERE {\n" + "\n".join(f"  {line}" for line in delete_scope.splitlines()) + "\n}"
        insert_block = "INSERT DATA {\n" + "\n".join(f"  {line}" for line in insert_payload.splitlines()) + "\n}"

    delete_stmt = "\n".join([delete_block, where_block])
    return "\n;\n".join([delete_stmt, insert_block])


def event_to_sparql(
    event: AasEvent | SubmodelEvent,
    base_uri: str,
    graph_iri: str | None = None,
    id_strategy: str = "url-encode",
    provenance: dict[str, Any] | None = None,
    enable_projection: bool = True,
) -> list[str]:
    """Convert a typed Kafka event to one or more SPARQL UPDATE statements."""

    def _with_projection(base_statements: list[str]) -> list[str]:
        if not enable_projection:
            return base_statements
        return base_statements + projection_statements_for_event(
            event=event,
            base_uri=base_uri,
            graph_iri=graph_iri,
            id_strategy=id_strategy,
        )

    if isinstance(event, AasEvent):
        if event.type in {AasEventType.AAS_CREATED, AasEventType.AAS_UPDATED}:
            if event.aas is None:
                raise ValueError(f"{event.type.value} requires event.aas")
            return _with_projection([
                build_upsert(
                    model=event.aas,
                    target_iri=aas_iri(base_uri, event.id, id_strategy=id_strategy),
                    graph_iri=graph_iri,
                    base_uri=base_uri,
                    id_strategy=id_strategy,
                    cascade_named_children=False,
                    provenance=provenance,
                )
            ])

        if event.type == AasEventType.AAS_DELETED:
            return _with_projection([
                build_delete(
                    target_iri=aas_iri(base_uri, event.id, id_strategy=id_strategy),
                    graph_iri=graph_iri,
                    cascade_named_children=False,
                )
            ])

        if event.type == AasEventType.SM_REF_ADDED:
            submodel_id = _submodel_id_from_reference(event)
            if not submodel_id:
                raise ValueError("SM_REF_ADDED requires submodelId or reference.keys[0].value")
            return _with_projection([
                build_link(
                    parent_iri=aas_iri(base_uri, event.id, id_strategy=id_strategy),
                    predicate_iri=AASNameSpace.AAS["AssetAdministrationShell/submodels"],
                    child_iri=submodel_iri(base_uri, submodel_id, id_strategy=id_strategy),
                    graph_iri=graph_iri,
                )
            ])

        if event.type == AasEventType.SM_REF_DELETED:
            submodel_id = _submodel_id_from_reference(event)
            if not submodel_id:
                raise ValueError("SM_REF_DELETED requires submodelId or reference.keys[0].value")
            return _with_projection([
                build_unlink(
                    parent_iri=aas_iri(base_uri, event.id, id_strategy=id_strategy),
                    predicate_iri=AASNameSpace.AAS["AssetAdministrationShell/submodels"],
                    child_iri=submodel_iri(base_uri, submodel_id, id_strategy=id_strategy),
                    graph_iri=graph_iri,
                )
            ])

        if event.type == AasEventType.ASSET_INFORMATION_SET:
            return _with_projection([
                _asset_information_set_statement(
                    event=event,
                    base_uri=base_uri,
                    graph_iri=graph_iri,
                    id_strategy=id_strategy,
                    provenance=provenance,
                )
            ])

    if isinstance(event, SubmodelEvent):
        if event.type in {SubmodelEventType.SM_CREATED, SubmodelEventType.SM_UPDATED}:
            if event.submodel is None:
                raise ValueError(f"{event.type.value} requires event.submodel")
            return _with_projection([
                build_upsert(
                    model=event.submodel,
                    target_iri=submodel_iri(base_uri, event.id, id_strategy=id_strategy),
                    graph_iri=graph_iri,
                    base_uri=base_uri,
                    id_strategy=id_strategy,
                    cascade_named_children=True,
                    provenance=provenance,
                )
            ])

        if event.type == SubmodelEventType.SM_DELETED:
            return _with_projection([
                build_delete(
                    target_iri=submodel_iri(base_uri, event.id, id_strategy=id_strategy),
                    graph_iri=graph_iri,
                    cascade_named_children=True,
                )
            ])

        if event.type in {SubmodelEventType.SME_CREATED, SubmodelEventType.SME_UPDATED}:
            if event.smElement is None:
                raise ValueError(f"{event.type.value} requires event.smElement")
            normalized_path = _ensure_path_has_id_short(event.smElementPath, event.smElement.idShort)
            if not normalized_path:
                raise ValueError(f"{event.type.value} requires smElementPath or smElement.idShort")
            return _with_projection([
                build_upsert(
                    model=event.smElement,
                    target_iri=submodel_element_iri(
                        base_uri,
                        event.id,
                        normalized_path,
                        id_strategy=id_strategy,
                    ),
                    graph_iri=graph_iri,
                    base_uri=base_uri,
                    id_strategy=id_strategy,
                    cascade_named_children=True,
                    provenance=provenance,
                    to_rdf_kwargs=_sme_to_rdf_kwargs(event.id, normalized_path, id_strategy=id_strategy),
                )
            ])

        if event.type == SubmodelEventType.SME_DELETED:
            normalized_path = _canonical_path(event.smElementPath)
            if not normalized_path:
                raise ValueError("SME_DELETED requires smElementPath")
            return _with_projection([
                build_delete(
                    target_iri=submodel_element_iri(base_uri, event.id, normalized_path, id_strategy=id_strategy),
                    graph_iri=graph_iri,
                    cascade_named_children=True,
                )
            ])

    raise ValueError(f"Unsupported event: {event}")
