from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

import rdflib
from .aas_models import base_64_url_encode, url_encode

from .events import AasEvent, AasEventType, SubmodelEvent, SubmodelEventType
from .iri import aas_iri, submodel_element_iri, submodel_iri, _submodel_elements_prefix
from .sparql import build_link, build_unlink

ARSO = rdflib.Namespace("https://w3id.org/2025/arso#")
ARSOX = rdflib.Namespace("https://w3id.org/aau-ra/arso-ext#")
APEX = rdflib.Namespace("https://w3id.org/2026/apex/")
CSS = rdflib.Namespace("http://www.w3id.org/hsu-aut/css#")
RDF = rdflib.RDF

_LOGGER = logging.getLogger("kg-bridge.projection")
_SEMANTIC_ID_MAP_ENV = "KG_SUBMODEL_SEMANTIC_ID_MAP_PATH"
_DEFAULT_SEMANTIC_ID_MAP_FILE = "submodel-semantic-id-map.phase2.json"

_FALLBACK_SEMANTIC_ID_TO_SUBMODEL_CLASS: dict[str, rdflib.URIRef] = {
    "https://admin-shell.io/idta/nameplate/3/0/Nameplate": ARSO["DigitalNameplateSubmodel"],
    "https://admin-shell.io/idta/HierarchicalStructures/1/1/Submodel": ARSO["HierarchicalStructuresSubmodel"],
    "https://admin-shell.io/idta/AssetInterfacesDescription/1/0/Submodel": ARSO["AIDSubmodel"],
    "https://admin-shell.io/idta/SubmodelTemplate/CapabilityDescription/1/0": ARSO["CapabilitiesSubmodel"],
    "https://admin-shell.io/idta/ControlComponentType/1/0": ARSO["SkillsSubmodel"],
    "https://admin-shell.io/idta-02003-2-0": ARSO["TechnicalDataSubmodel"],
}

_SHELL_CLASS_TYPES = [
    ARSOX["ResourceAssetAdministrationShell"],
    ARSOX["ProductAssetAdministrationShell"],
    ARSOX["ProcessAssetAdministrationShell"],
]

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
_FUZZY_PRODUCT_HINTS = ("hgh", "mim8")


def _normalize_semantic_id(value: str) -> str:
    return value.strip().rstrip("/")


def _default_semantic_id_map_path() -> Path:
    return Path(__file__).resolve().parents[1] / "contracts" / _DEFAULT_SEMANTIC_ID_MAP_FILE


def _load_semantic_id_to_submodel_class() -> dict[str, rdflib.URIRef]:
    mapping = {
        _normalize_semantic_id(semantic_id): class_iri
        for semantic_id, class_iri in _FALLBACK_SEMANTIC_ID_TO_SUBMODEL_CLASS.items()
    }

    configured_path = os.getenv(_SEMANTIC_ID_MAP_ENV, "").strip()
    map_path = Path(configured_path).expanduser() if configured_path else _default_semantic_id_map_path()
    if not map_path.exists():
        _LOGGER.info("Semantic-id map file not found at %s. Using built-in defaults.", map_path)
        return mapping

    try:
        payload = json.loads(map_path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - defensive parsing guard
        _LOGGER.warning("Failed to parse semantic-id map file %s: %s. Using built-in defaults.", map_path, exc)
        return mapping

    entries = payload.get("mappings") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        _LOGGER.warning("Semantic-id map file %s is missing a 'mappings' array. Using built-in defaults.", map_path)
        return mapping

    loaded_count = 0
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        semantic_id = entry.get("semantic_id")
        class_iri = entry.get("class_iri")
        if not isinstance(semantic_id, str) or not semantic_id.strip():
            continue
        if not isinstance(class_iri, str) or not class_iri.strip():
            continue
        mapping[_normalize_semantic_id(semantic_id)] = rdflib.URIRef(class_iri.strip())
        loaded_count += 1

    _LOGGER.info("Loaded %d semantic-id mapping(s) from %s", loaded_count, map_path)
    return mapping


_SEMANTIC_ID_TO_SUBMODEL_CLASS = _load_semantic_id_to_submodel_class()
_KNOWN_SUBMODEL_CLASSES = sorted({uri for uri in _SEMANTIC_ID_TO_SUBMODEL_CLASS.values()}, key=str)


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

    return _SEMANTIC_ID_TO_SUBMODEL_CLASS.get(_normalize_semantic_id(semantic_id))


def _entity_iri(base_uri: str, kind: str, aas_id: str, id_strategy: str) -> rdflib.URIRef:
    if id_strategy == "identity":
        # Synthetic resource/product/process individuals are not AAS objects and have no
        # IRI of their own, so under identity (empty base_uri) they get a dedicated urn:
        # namespace instead of an invalid scheme-less IRI. The aas_id is percent-encoded
        # so the URN is always well-formed regardless of the source identifier shape.
        return rdflib.URIRef(f"urn:kg:entity:{kind}:{url_encode(aas_id)}")
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

    asset_information = getattr(aas, "assetInformation", None) if aas is not None else None
    if asset_information is None:
        asset_information = getattr(event, "assetInformation", None)

    if asset_information is not None:
        for attr in ("globalAssetId", "assetType", "assetKind"):
            value = getattr(asset_information, attr, None)
            if isinstance(value, str) and value:
                values.append(value)

    return " ".join(values).lower()


def _explicit_shell_kind(event: AasEvent) -> str | None:
    aas = getattr(event, "aas", None)
    explicit_values: list[str] = []

    if aas is not None:
        category = getattr(aas, "category", None)
        if isinstance(category, str) and category.strip():
            explicit_values.append(category.strip())

        asset_information = getattr(aas, "assetInformation", None)
    else:
        asset_information = getattr(event, "assetInformation", None)

    if asset_information is not None:
        for attr in ("assetType", "globalAssetId"):
            value = getattr(asset_information, attr, None)
            if isinstance(value, str) and value.strip():
                explicit_values.append(value.strip())

    for raw in explicit_values:
        lowered = raw.lower()
        token = lowered.split("#")[-1].split("/")[-1]
        for candidate in (lowered, token):
            if candidate in {"product", "css:product", "apex:product"}:
                return "product"
            if candidate in {"process", "css:process", "apex:process"}:
                return "process"
            if candidate in {"resource", "css:resource", "apex:resource"}:
                return "resource"
    return None


def _match_hint(text: str, hint: str, fuzzy: bool = False) -> bool:
    if fuzzy:
        return hint in text
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(hint)}(?![a-z0-9])", text))


def _hint_score(text: str, hints: tuple[str, ...], fuzzy_hints: tuple[str, ...] = ()) -> int:
    return sum(1 for hint in hints if _match_hint(text, hint, fuzzy=hint in fuzzy_hints))


def _infer_shell_kind(event: AasEvent) -> str:
    explicit_kind = _explicit_shell_kind(event)
    if explicit_kind is not None:
        return explicit_kind

    text = _text_fields_for_shell(event)
    product_score = _hint_score(text, _PRODUCT_HINTS, fuzzy_hints=_FUZZY_PRODUCT_HINTS)
    process_score = _hint_score(text, _PROCESS_HINTS)

    if product_score > 0 and process_score == 0:
        return "product"
    if process_score > 0 and product_score == 0:
        return "process"
    if _hint_score(text, _RESOURCE_HINTS) > 0:
        return "resource"
    return "resource"


def _delete_where_entity_links_to_shell(shell: rdflib.URIRef, graph_iri: str | None) -> str:
    # Clean up the canonical resource-AAS link predicate on shell updates.
    predicates = [ARSO["hasResourceAAS"]]
    values = " ".join(predicate.n3() for predicate in predicates)

    if graph_iri:
        return (
            "DELETE {\n"
            f"  GRAPH <{graph_iri}> {{\n"
            "    ?entity ?p "
            + shell.n3()
            + " .\n"
            "  }\n"
            "}\n"
            "WHERE {\n"
            f"  GRAPH <{graph_iri}> {{\n"
            "    ?entity ?p "
            + shell.n3()
            + " .\n"
            f"    VALUES ?p {{ {values} }}\n"
            "  }\n"
            "}"
        )

    return (
        "DELETE {\n"
        "  ?entity ?p "
        + shell.n3()
        + " .\n"
        "}\n"
        "WHERE {\n"
        "  ?entity ?p "
        + shell.n3()
        + " .\n"
        f"  VALUES ?p {{ {values} }}\n"
        "}"
    )


def _delete_ref_keys(sme_node: rdflib.URIRef, graph_iri: str | None) -> str:
    """Delete all apex:hasRefKey child nodes for an SME (cascade delete on update)."""
    if graph_iri:
        return (
            "DELETE {\n"
            f"  GRAPH <{graph_iri}> {{\n"
            f"    {sme_node.n3()} {APEX['hasRefKey'].n3()} ?key .\n"
            "    ?key ?p ?o .\n"
            "  }\n"
            "}\n"
            "WHERE {\n"
            f"  GRAPH <{graph_iri}> {{\n"
            f"    {sme_node.n3()} {APEX['hasRefKey'].n3()} ?key .\n"
            "    ?key ?p ?o .\n"
            "  }\n"
            "}"
        )
    return (
        "DELETE {\n"
        f"  {sme_node.n3()} {APEX['hasRefKey'].n3()} ?key .\n"
        "  ?key ?p ?o .\n"
        "}\n"
        "WHERE {\n"
        f"  {sme_node.n3()} {APEX['hasRefKey'].n3()} ?key .\n"
        "  ?key ?p ?o .\n"
        "}"
    )


def _delete_where_subject_predicates(
    subject: rdflib.URIRef,
    predicates: list[rdflib.URIRef],
    graph_iri: str | None,
) -> str:
    if not predicates:
        return ""

    # VALUES is not legal inside DELETE WHERE { } in SPARQL 1.1.
    # Use DELETE { } WHERE { VALUES } instead.
    values = " ".join(predicate.n3() for predicate in predicates)
    if graph_iri:
        return (
            "DELETE {\n"
            f"  GRAPH <{graph_iri}> {{\n"
            f"    {subject.n3()} ?p ?o .\n"
            "  }\n"
            "}\n"
            "WHERE {\n"
            f"  GRAPH <{graph_iri}> {{\n"
            f"    {subject.n3()} ?p ?o .\n"
            f"    VALUES ?p {{ {values} }}\n"
            "  }\n"
            "}"
        )

    return (
        "DELETE {\n"
        f"  {subject.n3()} ?p ?o .\n"
        "}\n"
        "WHERE {\n"
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

    # VALUES is not legal inside DELETE WHERE { } — use DELETE { } WHERE { VALUES }.
    values = " ".join(class_iri.n3() for class_iri in classes)
    if graph_iri:
        return (
            "DELETE {\n"
            f"  GRAPH <{graph_iri}> {{\n"
            f"    {subject.n3()} a ?old_type .\n"
            "  }\n"
            "}\n"
            "WHERE {\n"
            f"  GRAPH <{graph_iri}> {{\n"
            f"    {subject.n3()} a ?old_type .\n"
            f"    VALUES ?old_type {{ {values} }}\n"
            "  }\n"
            "}"
        )

    return (
        "DELETE {\n"
        f"  {subject.n3()} a ?old_type .\n"
        "}\n"
        "WHERE {\n"
        f"  {subject.n3()} a ?old_type .\n"
        f"  VALUES ?old_type {{ {values} }}\n"
        "}"
    )


# ── SM_CREATED tree-walk helpers ──────────────────────────────────────────────

def _delete_submodel_mirrored_elements(
    submodel_id: str,
    base_uri: str,
    graph_iri: str | None,
    id_strategy: str,
) -> str:
    """Cascade-delete all MirroredSubmodelElement nodes under a submodel (SM_UPDATED)."""
    sme_prefix = _submodel_elements_prefix(submodel_id, id_strategy)
    full_prefix = f"{base_uri}{sme_prefix}"
    if graph_iri:
        return (
            f"DELETE {{\n"
            f"  GRAPH <{graph_iri}> {{\n"
            f"    ?sme ?p ?o .\n"
            f"  }}\n"
            f"}}\n"
            f"WHERE {{\n"
            f"  GRAPH <{graph_iri}> {{\n"
            f"    ?sme a {APEX['MirroredSubmodelElement'].n3()} .\n"
            f"    FILTER(STRSTARTS(STR(?sme), \"{full_prefix}\"))\n"
            f"    ?sme ?p ?o .\n"
            f"  }}\n"
            f"}}"
        )
    return (
        f"DELETE {{\n"
        f"  ?sme ?p ?o .\n"
        f"}}\n"
        f"WHERE {{\n"
        f"  ?sme a {APEX['MirroredSubmodelElement'].n3()} .\n"
        f"  FILTER(STRSTARTS(STR(?sme), \"{full_prefix}\"))\n"
        f"  ?sme ?p ?o .\n"
        f"}}"
    )


def _walk_element_tree(
    element: Any,
    submodel_id: str,
    parent_path: str,
    lines: list[str],
) -> None:
    """Recursively walk a submodel element tree, emitting MirroredSubmodelElement
    triples for every element (including nested collections and lists).

    Mirrors the same shape as the SME_UPDATED path, so materialization rules
    (040/041/042) work against both initial (SM_CREATED) and incremental
    (SME_UPDATED) data.
    """
    id_short = getattr(element, "idShort", None)
    if not id_short:
        return
    # Build canonical path: parent_path + "." separator + id_short
    path = f"{parent_path}.{id_short}" if parent_path else id_short

    sme_node = submodel_element_iri("", submodel_id, path, "identity")

    # Type + path + modelType (same as SME_UPDATED)
    model_type = getattr(element, "modelType", "")
    lines += [
        f"{sme_node.n3()} a {APEX['MirroredSubmodelElement'].n3()} .",
        f"{sme_node.n3()} {APEX['smElementPath'].n3()} {rdflib.Literal(path).n3()} .",
        f"{sme_node.n3()} {APEX['smElementModelType'].n3()} {rdflib.Literal(str(model_type)).n3()} .",
    ]

    # Value (for Property elements)
    value = getattr(element, "value", None)
    if isinstance(value, (str, int, float, bool)):
        lines.append(f"{sme_node.n3()} {APEX['smElementValue'].n3()} {rdflib.Literal(value).n3()} .")

    # Reference elements (hasRefKey children + refType)
    if hasattr(value, "keys") and hasattr(value, "type"):
        ref_type_str = value.type.value if hasattr(value.type, "value") else str(value.type)
        lines.append(f"{sme_node.n3()} {APEX['smElementRefType'].n3()} {rdflib.Literal(ref_type_str).n3()} .")
        for idx, key in enumerate(value.keys or []):
            key_iri = rdflib.URIRef(f"{sme_node}/ref-key/{idx}")
            key_type_str = key.type.value if hasattr(key.type, "value") else str(key.type)
            lines += [
                f"{sme_node.n3()} {APEX['hasRefKey'].n3()} {key_iri.n3()} .",
                f"{key_iri.n3()} a {APEX['RefKey'].n3()} .",
                f"{key_iri.n3()} {APEX['refKeyIndex'].n3()} {rdflib.Literal(idx, datatype=rdflib.XSD.nonNegativeInteger).n3()} .",
                f"{key_iri.n3()} {APEX['refKeyType'].n3()} {rdflib.Literal(key_type_str).n3()} .",
                f"{key_iri.n3()} {APEX['refKeyValue'].n3()} {rdflib.Literal(str(key.value or '')).n3()} .",
            ]

    # Semantic ID
    semantic_id = _semantic_id_from_model(element)
    if semantic_id:
        lines.append(f"{sme_node.n3()} {APEX['smElementSemanticId'].n3()} {rdflib.Literal(semantic_id).n3()} .")

    # Recurse into collections and lists
    if isinstance(value, list):
        for idx, child in enumerate(value):
            child_model_type = getattr(child, "modelType", "")
            if child_model_type == "SubmodelElementList":
                child_path = f"{path}[{idx}]"
                _walk_element_tree(child, submodel_id, child_path, lines)
            else:
                _walk_element_tree(child, submodel_id, path, lines)


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
                _LOGGER.warning("AAS_CREATED/UPDATED skipped: event.aas is None (id=%s)", event.id)
                return statements

            shell = aas_iri(base_uri, event.id, id_strategy=id_strategy)
            statements.append(
                _delete_where_subject_predicates(
                    shell,
                    [APEX["aasIdShort"]],
                    graph_iri,
                )
            )
            statements.append(_delete_where_subject_types(shell, _SHELL_CLASS_TYPES, graph_iri))
            statements.append(_delete_where_entity_links_to_shell(shell, graph_iri))

            # Store the AAS idShort as a literal so SPARQL queries can derive
            # PDDL object names without reversing the identity IRI or calling AAS REST.
            id_short = getattr(event.aas, "idShort", None) or ""
            if id_short:
                id_short_literal = rdflib.Literal(id_short).n3()
                if graph_iri:
                    statements.append(
                        "INSERT DATA {\n"
                        f"  GRAPH <{graph_iri}> {{\n"
                        f"    {shell.n3()} {APEX['aasIdShort'].n3()} {id_short_literal} .\n"
                        "  }\n"
                        "}"
                    )
                else:
                    statements.append(
                        "INSERT DATA {\n"
                        f"  {shell.n3()} {APEX['aasIdShort'].n3()} {id_short_literal} .\n"
                        "}"
                    )

            kind = _infer_shell_kind(event)

            # Type the AAS shell directly — no synthetic entity node needed.
            # All three kinds use the shell IRI as the primary identity.
            kind_type = {
                "product": ARSOX["ProductAssetAdministrationShell"],
                "process": ARSOX["ProcessAssetAdministrationShell"],
            }.get(kind, ARSOX["ResourceAssetAdministrationShell"])

            statements.append(
                build_link(parent_iri=shell, predicate_iri=RDF.type,
                           child_iri=kind_type, graph_iri=graph_iri)
            )

            # Derive arso:hasSubmodel links from the AAS's submodels references.
            # BaSyx does not publish SM_REF_ADDED events, so this is the
            # authoritative source of the AAS-to-submodel relationship.
            statements.append(
                _delete_where_subject_predicates(
                    shell,
                    [ARSO["hasSubmodel"]],
                    graph_iri,
                )
            )
            aas = event.aas
            submodels = getattr(aas, "submodels", None)
            if submodels:
                for ref in submodels:
                    keys = getattr(ref, "keys", None)
                    if not keys:
                        continue
                    submodel_id = keys[0].value if keys[0].value else None
                    if not submodel_id:
                        continue
                    statements.append(
                        build_link(
                            parent_iri=shell,
                            predicate_iri=ARSO["hasSubmodel"],
                            child_iri=submodel_iri(base_uri, submodel_id, id_strategy=id_strategy),
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
                stmt = build_link(
                    parent_iri=aas_iri(base_uri, event.id, id_strategy=id_strategy),
                    predicate_iri=ARSO["hasSubmodel"],
                    child_iri=submodel_iri(base_uri, submodel_id, id_strategy=id_strategy),
                    graph_iri=graph_iri,
                )
                _LOGGER.info("SM_REF_ADDED: AAS=%s submodel=%s stmt=[%s...%s]", event.id, submodel_id, stmt[:80], stmt[-40:])
                statements.append(stmt)
            else:
                _LOGGER.warning("SM_REF_ADDED skipped: no submodelId in event (id=%s)", event.id)
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
        if event.submodel is None:
            _LOGGER.warning("SM_CREATED/UPDATED skipped: event.submodel is None (id=%s)", event.id)
            return []

        submodel_node = submodel_iri(base_uri, event.id, id_strategy=id_strategy)
        elements = getattr(event.submodel, "submodelElements", None)
        if not isinstance(elements, list) or len(elements) == 0:
            return []

        is_update = (event.type == SubmodelEventType.SM_UPDATED)
        if is_update:
            # Cascade-delete all previously mirrored elements for this submodel.
            statements.append(
                _delete_submodel_mirrored_elements(
                    event.id, base_uri, graph_iri, id_strategy
                )
            )

        # Walk the submodelElements tree and emit MirroredSubmodelElement nodes.
        insert_lines: list[str] = []
        for element in elements:
            _walk_element_tree(element, str(submodel_node), "", insert_lines)

        if insert_lines:
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

    if event.type in {SubmodelEventType.SME_CREATED, SubmodelEventType.SME_UPDATED}:
        if event.smElement is None:
            _LOGGER.warning("SME_CREATED/UPDATED skipped: event.smElement is None (id=%s)", event.id)
            return statements

        normalized_path = _ensure_path_has_id_short(event.smElementPath, getattr(event.smElement, "idShort", None))
        if not normalized_path:
            _LOGGER.warning("SME_CREATED/UPDATED skipped: empty normalized_path (id=%s path=%s)", event.id, event.smElementPath)
            return statements

        sme_node = submodel_element_iri(base_uri, event.id, normalized_path, id_strategy=id_strategy)

        statements.append(
            _delete_where_subject_predicates(
                sme_node,
                [
                    APEX["smElementPath"],
                    APEX["smElementValue"],
                    APEX["smElementModelType"],
                    APEX["smElementSemanticId"],
                    APEX["smElementRefType"],
                ],
                graph_iri,
            )
        )
        # Cascade-delete any previously stored ref-key child nodes for this SME.
        statements.append(_delete_ref_keys(sme_node, graph_iri))

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
        elif hasattr(value, "keys") and hasattr(value, "type"):
            # ReferenceElement: store the reference type + one child node per key.
            # Key IRIs: <sme_iri>/ref-key/<N> — readable under the identity IRI strategy.
            ref_type_str = value.type.value if hasattr(value.type, "value") else str(value.type)
            insert_lines.append(
                f"{sme_node.n3()} {APEX['smElementRefType'].n3()} {rdflib.Literal(ref_type_str).n3()} ."
            )
            for idx, key in enumerate(value.keys or []):
                key_iri = rdflib.URIRef(f"{sme_node}/ref-key/{idx}")
                key_type_str = key.type.value if hasattr(key.type, "value") else str(key.type)
                insert_lines += [
                    f"{sme_node.n3()} {APEX['hasRefKey'].n3()} {key_iri.n3()} .",
                    f"{key_iri.n3()} a {APEX['RefKey'].n3()} .",
                    f"{key_iri.n3()} {APEX['refKeyIndex'].n3()} {rdflib.Literal(idx, datatype=rdflib.XSD.nonNegativeInteger).n3()} .",
                    f"{key_iri.n3()} {APEX['refKeyType'].n3()} {rdflib.Literal(key_type_str).n3()} .",
                    f"{key_iri.n3()} {APEX['refKeyValue'].n3()} {rdflib.Literal(str(key.value or '')).n3()} .",
                ]

        semantic_id = _semantic_id_from_model(event.smElement)
        if semantic_id:
            _LOGGER.info("SME: setting smElementSemanticId=%s for %s", semantic_id, normalized_path)
            insert_lines.append(
                f"{sme_node.n3()} {APEX['smElementSemanticId'].n3()} {rdflib.Literal(semantic_id).n3()} ."
            )
        else:
            _LOGGER.warning("SME: no semanticId found in event for %s (id=%s)", normalized_path, event.id)

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
