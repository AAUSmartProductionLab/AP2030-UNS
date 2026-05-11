from __future__ import annotations

import re

import rdflib

from py_aas_rdf.models import base_64_url_encode, url_encode

_LIST_TOKEN_RE = re.compile(r"^(?P<name>[^\[\]]+?)(?:\[(?P<index>\d+)\])?$")


def _encode_identifier(value: str, id_strategy: str) -> str:
    if id_strategy == "base64-url-encode":
        return base_64_url_encode(value)
    return url_encode(value)


def _canonical_path_tokens(sm_element_path: str) -> list[str]:
    normalized = (sm_element_path or "").strip().replace("/", ".")
    return [token for token in normalized.split(".") if token]


def _encode_path_token(token: str) -> str:
    parsed = _LIST_TOKEN_RE.match(token)
    if not parsed:
        return token

    name = parsed.group("name")
    index = parsed.group("index")
    if index is None:
        return name

    return f"{name}%5B{index}%5D"


def _encode_sm_element_path(sm_element_path: str) -> str:
    tokens = _canonical_path_tokens(sm_element_path)
    return ".".join(_encode_path_token(token) for token in tokens)


def _submodel_elements_prefix(submodel_id: str, id_strategy: str) -> str:
    if id_strategy == "base64-url-encode":
        return f"{base_64_url_encode(submodel_id)}/submodel-elements/"
    return url_encode(f"{submodel_id}/submodel-elements/")


def aas_iri(base_uri: str, aas_id: str, id_strategy: str = "url-encode") -> rdflib.URIRef:
    return rdflib.URIRef(f"{base_uri}{_encode_identifier(aas_id, id_strategy)}")


def submodel_iri(base_uri: str, submodel_id: str, id_strategy: str = "url-encode") -> rdflib.URIRef:
    return rdflib.URIRef(f"{base_uri}{_encode_identifier(submodel_id, id_strategy)}")


def submodel_element_iri(
    base_uri: str,
    submodel_id: str,
    sm_element_path: str,
    id_strategy: str = "url-encode",
) -> rdflib.URIRef:
    """Build a SubmodelElement IRI from a BaSyx-style path.

    Expected path format uses "." between collection/entity children and "[idx]"
    for list positions (e.g., "Col1.List1[1].P2"). List index markers are converted
    to the encoded form used by the static serializer ("%5Bidx%5D").
    """

    encoded_path = _encode_sm_element_path(sm_element_path)
    prefix = _submodel_elements_prefix(submodel_id, id_strategy)
    return rdflib.URIRef(f"{base_uri}{prefix}{encoded_path}")
