from __future__ import annotations

from typing import Any

import rdflib
from py_aas_rdf.models import base_64_url_encode, url_encode

from .events import AasEvent, AasEventType, SubmodelEvent, SubmodelEventType
from .iri import aas_iri, submodel_element_iri, submodel_iri
from .sparql import build_link, build_unlink

ARSO = rdflib.Namespace("https://w3id.org/2025/arso#")
ARSOX = rdflib.Namespace("https://w3id.org/aau-ra/arso-ext#")
APEX = rdflib.Namespace("https://w3id.org/2026/apex/")
CSS = rdflib.Namespace("http://www.w3id.org/hsu-aut/css#")
RDF = rdflib.RDF

_SEMANTIC_ID_TO_SUBMODEL_CLASS: dict[str, rdflib.URIRef] = {
    "https://admin-shell.io/idta/nameplate/3/0/Nameplate": ARSO["DigitalNameplateSubmodel"],
    "https://admin-shell.io/idta/HierarchicalStructures/1/1/Submodel": ARSO["HierarchicalStructuresSubmodel"],
    "https://admin-shell.io/idta/AssetInterfacesDescription/1/0/Submodel": ARSO["AIDSubmodel"],
    "https://admin-shell.io/idta/SubmodelTemplate/CapabilityDescription/1/0": ARSO["CapabilitiesSubmodel"],
    "https://admin-shell.io/idta/ControlComponentType/1/0": ARSO["SkillsSubmodel"],
    "https://admin-shell.io/idta-02003-2-0": ARSO["TechnicalDataSubmodel"],
}

_KNOWN_SUBMODEL_CLASSES = sorted({uri for uri in _SEMANTIC_ID_TO_SUBMODEL_CLASS.values()}, key=str)
_SHELL_CLASS_TYPES = [ARSOX["ProductAssetAdministrationShell"], ARSOX["ProcessAssetAdministrationShell"]]

_PRODUCT_HINTS = ("product", "batch", "lot", "hgh", "mim8")
_PROCESS_HINTS = ("process", "operation", "workflow", "routing", "recipe")
_RESOURCE_HINTS = (
    "resource",
    "station",
    "module",
    "system",
    "robot",
    "controller",
    "cell",
    "line",
    "transport",
    "shuttle",
    "planner",
    "orchestrator",
)


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


def _submodel_id_from_reference(event: AasEvent) -> str | None:
    if event.submodelId:
        return event.submodelId

    if event.reference and event.reference.keys:
        first_key = event.reference.keys[0]
        if first_key.value:
            return first_key.value

    return None


def _semantic_id_from_model(model: Any) -> str | None:
    semantic_ref = getattr(model, "semanticId", None)
    if semantic_ref is None:
        return None

    keys = getattr(semantic_ref, "keys", None)
    if not isinstance(keys, list):
        return None

    for key in keys:
        value = getattr(key, "value", None)
        if isinstance(value, str) and value.strip():
            return value.strip()

    return None


def _class_for_semantic_id(semantic_id: str | None) -> rdflib.URIRef | None:
    if not semantic_id:
        return None

    normalized = semantic_id.rstrip("/")
    for known_semantic_id, mapped_class in _SEMANTIC_ID_TO_SUBMODEL_CLASS.items():
        if normalized == known_semantic_id.rstrip("/"):
            return mapped_class
    return None


def _entity_iri(base_uri: str, kind: str, aas_id: str, id_strategy: str) -> rdflib.URIRef:
    key = f"entities/{kind}/{aas_id}"
    if id_strategy == "base64-url-encode":
        encoded = base_64_url_encode(key)
    else:
        encoded = url_encode(key)
    return rdflib.URIRef(f"{base_uri}{encoded}")


def _text_fields_for_shell(event: AasEvent) -> str:
    values: list[str] = [str(event.id)]
    aas = getattr(event, "aas", None)
    if aas is not None:
        for attr in ("id", "idShort", "category"):
            value = getattr(aas, attr, None)
            if isinstance(value, str) and value:
                values.append(value)
    return " ".join(values).lower()


def _infer_shell_kind(event: AasEvent) -> str:
    text = _text_fields_for_shell(event)

    if any(token in text for token in _PRODUCT_HINTS):
        return "product"
    if any(token in text for token in _PROCESS_HINTS):
        return "process"
    if any(token in text for token in _RESOURCE_HINTS):
        return "resource"
    return "resource"


def _delete_where_entity_links_to_shell(shell: rdflib.URIRef, graph_iri: str | None) -> str:
    predicates = [ARSO["hasAAS"], ARSOX["hasAASForProduct"], ARSOX["hasAASForProcess"]]
    values = " ".join(predicate.n3() for predicate in predicates)

    if graph_iri:
        return (
            "DELETE WHERE {\n"
            f"  GRAPH <{graph_iri}> {{\n"
            "    ?entity ?p "
            + shell.n3()
            + " .\n"
            f"    VALUES ?p {{ {values} }}\n"
            "  }\n"
            "}"
        )

    return (
        "DELETE WHERE {\n"
        "  ?entity ?p "
        + shell.n3()
        + " .\n"
        f"  VALUES ?p {{ {values} }}\n"
        "}"
    )


def _delete_where_subject_predicates(
    subject: rdflib.URIRef,
    predicates: list[rdflib.URIRef],
    graph_iri: str | None,
) -> str:
    if not predicates:
        return ""

    values = " ".join(predicate.n3() for predicate in predicates)
    if graph_iri:
        return (
            "DELETE WHERE {\n"
            f"  GRAPH <{graph_iri}> {{\n"
            f"    {subject.n3()} ?p ?o .\n"
            f"    VALUES ?p {{ {values} }}\n"
            "  }\n"
            "}"
        )

    return (
        "DELETE WHERE {\n"
        f"  {subject.n3()} ?p ?o .\n"
        f"  VALUES ?p {{ {values} }}\n"
        "}"
    )


def _delete_where_subject_types(
    subject: rdflib.URIRef,
    classes: list[rdflib.URIRef],
    graph_iri: str | None,
) -> str:
    if not classes:
        return ""

    values = " ".join(class_iri.n3() for class_iri in classes)
    if graph_iri:
        return (
            "DELETE WHERE {\n"
            f"  GRAPH <{graph_iri}> {{\n"
            f"    {subject.n3()} a ?old_type .\n"
            f"    VALUES ?old_type {{ {values} }}\n"
            "  }\n"
            "}"
        )

    return (
        "DELETE WHERE {\n"
        f"  {subject.n3()} a ?old_type .\n"
        f"  VALUES ?old_type {{ {values} }}\n"
        "}"
    )


def projection_statements_for_event(
    event: AasEvent | SubmodelEvent,
    base_uri: str,
    graph_iri: str | None,
    id_strategy: str,
) -> list[str]:
    statements: list[str] = []

    if isinstance(event, AasEvent):
        if event.type in {AasEventType.AAS_CREATED, AasEventType.AAS_UPDATED}:
            if event.aas is None:
                return statements

            shell = aas_iri(base_uri, event.id, id_strategy=id_strategy)
            statements.append(
                _delete_where_subject_predicates(
                    shell,
                    [ARSO["representsResource"], ARSOX["representsProduct"], ARSOX["representsProcess"]],
                    graph_iri,
                )
            )
            statements.append(_delete_where_subject_types(shell, _SHELL_CLASS_TYPES, graph_iri))
            statements.append(_delete_where_entity_links_to_shell(shell, graph_iri))

            kind = _infer_shell_kind(event)
            entity = _entity_iri(base_uri, kind, event.id, id_strategy=id_strategy)

            if kind == "product":
                statements.append(
                    build_link(
                        parent_iri=shell,
                        predicate_iri=ARSOX["representsProduct"],
                        child_iri=entity,
                        graph_iri=graph_iri,
                    )
                )
                statements.append(
                    build_link(
                        parent_iri=shell,
                        predicate_iri=RDF.type,
                        child_iri=ARSOX["ProductAssetAdministrationShell"],
                        graph_iri=graph_iri,
                    )
                )
                statements.append(
                    build_link(
                        parent_iri=entity,
                        predicate_iri=RDF.type,
                        child_iri=CSS["Product"],
                        graph_iri=graph_iri,
                    )
                )
                statements.append(
                    build_link(
                        parent_iri=entity,
                        predicate_iri=ARSOX["hasAASForProduct"],
                        child_iri=shell,
                        graph_iri=graph_iri,
                    )
                )
            elif kind == "process":
                statements.append(
                    build_link(
                        parent_iri=shell,
                        predicate_iri=ARSOX["representsProcess"],
                        child_iri=entity,
                        graph_iri=graph_iri,
                    )
                )
                statements.append(
                    build_link(
                        parent_iri=shell,
                        predicate_iri=RDF.type,
                        child_iri=ARSOX["ProcessAssetAdministrationShell"],
                        graph_iri=graph_iri,
                    )
                )
                statements.append(
                    build_link(
                        parent_iri=entity,
                        predicate_iri=RDF.type,
                        child_iri=CSS["Process"],
                        graph_iri=graph_iri,
                    )
                )
                statements.append(
                    build_link(
                        parent_iri=entity,
                        predicate_iri=ARSOX["hasAASForProcess"],
                        child_iri=shell,
                        graph_iri=graph_iri,
                    )
                )
            else:
                statements.append(
                    build_link(
                        parent_iri=shell,
                        predicate_iri=ARSO["representsResource"],
                        child_iri=entity,
                        graph_iri=graph_iri,
                    )
                )
                statements.append(
                    build_link(
                        parent_iri=entity,
                        predicate_iri=RDF.type,
                        child_iri=CSS["Resource"],
                        graph_iri=graph_iri,
                    )
                )
                statements.append(
                    build_link(
                        parent_iri=entity,
                        predicate_iri=ARSO["hasAAS"],
                        child_iri=shell,
                        graph_iri=graph_iri,
                    )
                )

            return [statement for statement in statements if statement]

        if event.type == AasEventType.AAS_DELETED:
            shell = aas_iri(base_uri, event.id, id_strategy=id_strategy)
            statements.append(
                _delete_where_subject_predicates(
                    shell,
                    [ARSO["representsResource"], ARSOX["representsProduct"], ARSOX["representsProcess"]],
                    graph_iri,
                )
            )
            statements.append(_delete_where_subject_types(shell, _SHELL_CLASS_TYPES, graph_iri))
            statements.append(_delete_where_entity_links_to_shell(shell, graph_iri))
            return [statement for statement in statements if statement]

        if event.type == AasEventType.SM_REF_ADDED:
            submodel_id = _submodel_id_from_reference(event)
            if submodel_id:
                statements.append(
                    build_link(
                        parent_iri=aas_iri(base_uri, event.id, id_strategy=id_strategy),
                        predicate_iri=ARSO["hasSubmodel"],
                        child_iri=submodel_iri(base_uri, submodel_id, id_strategy=id_strategy),
                        graph_iri=graph_iri,
                    )
                )
            return statements

        if event.type == AasEventType.SM_REF_DELETED:
            submodel_id = _submodel_id_from_reference(event)
            if submodel_id:
                statements.append(
                    build_unlink(
                        parent_iri=aas_iri(base_uri, event.id, id_strategy=id_strategy),
                        predicate_iri=ARSO["hasSubmodel"],
                        child_iri=submodel_iri(base_uri, submodel_id, id_strategy=id_strategy),
                        graph_iri=graph_iri,
                    )
                )
            return statements

        return statements

    if event.type in {SubmodelEventType.SM_CREATED, SubmodelEventType.SM_UPDATED}:
        semantic_id = _semantic_id_from_model(event.submodel) if event.submodel is not None else None
        mapped_class = _class_for_semantic_id(semantic_id)
        submodel_node = submodel_iri(base_uri, event.id, id_strategy=id_strategy)

        statements.append(_delete_where_subject_types(submodel_node, _KNOWN_SUBMODEL_CLASSES, graph_iri))
        statements.append(
            _delete_where_subject_predicates(submodel_node, [APEX["sourceSemanticId"]], graph_iri)
        )

        if mapped_class is not None:
            statements.append(
                build_link(
                    parent_iri=submodel_node,
                    predicate_iri=RDF.type,
                    child_iri=mapped_class,
                    graph_iri=graph_iri,
                )
            )

        if semantic_id:
            literal = rdflib.Literal(semantic_id).n3()
            if graph_iri:
                statements.append(
                    "INSERT DATA {\n"
                    f"  GRAPH <{graph_iri}> {{\n"
                    f"    {submodel_node.n3()} {APEX['sourceSemanticId'].n3()} {literal} .\n"
                    "  }\n"
                    "}"
                )
            else:
                statements.append(
                    "INSERT DATA {\n"
                    f"  {submodel_node.n3()} {APEX['sourceSemanticId'].n3()} {literal} .\n"
                    "}"
                )

        return [statement for statement in statements if statement]

    if event.type in {SubmodelEventType.SME_CREATED, SubmodelEventType.SME_UPDATED}:
        if event.smElement is None:
            return statements

        normalized_path = _ensure_path_has_id_short(event.smElementPath, getattr(event.smElement, "idShort", None))
        if not normalized_path:
            return statements

        sme_node = submodel_element_iri(base_uri, event.id, normalized_path, id_strategy=id_strategy)

        statements.append(
            _delete_where_subject_predicates(
                sme_node,
                [
                    APEX["smElementPath"],
                    APEX["smElementValue"],
                    APEX["smElementModelType"],
                ],
                graph_iri,
            )
        )

        statements.append(
            build_link(
                parent_iri=sme_node,
                predicate_iri=RDF.type,
                child_iri=APEX["MirroredSubmodelElement"],
                graph_iri=graph_iri,
            )
        )

        path_literal = rdflib.Literal(_canonical_path(normalized_path)).n3()
        model_type = getattr(event.smElement, "modelType", "")
        model_type_literal = rdflib.Literal(str(model_type)).n3()

        insert_lines = [
            f"{sme_node.n3()} {APEX['smElementPath'].n3()} {path_literal} .",
            f"{sme_node.n3()} {APEX['smElementModelType'].n3()} {model_type_literal} .",
        ]

        value = getattr(event.smElement, "value", None)
        if isinstance(value, (str, int, float, bool)):
            insert_lines.append(f"{sme_node.n3()} {APEX['smElementValue'].n3()} {rdflib.Literal(value).n3()} .")

        if graph_iri:
            statements.append(
                "INSERT DATA {\n"
                f"  GRAPH <{graph_iri}> {{\n"
                + "\n".join(f"    {line}" for line in insert_lines)
                + "\n"
                "  }\n"
                "}"
            )
        else:
            statements.append("INSERT DATA {\n" + "\n".join(f"  {line}" for line in insert_lines) + "\n}")

        return [statement for statement in statements if statement]

    return statements
