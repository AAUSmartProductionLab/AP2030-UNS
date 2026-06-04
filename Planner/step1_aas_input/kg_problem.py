"""Infer PDDL Problem init-state from the live KG (Phase 4C option B).

Strategy:
- Runs the existing kg-bridge CONSTRUCT views (Operational, Occupied, InRange,
  ResourceAt, ProductAt) to get current predicate state.
- Parses the turtle CONSTRUCT output with rdflib to extract argument bindings.
- Maps KG instance IRIs → PDDL object names via apex:aasIdShort on the AAS node.
- Returns init terms that AUGMENT the AAS-derived init: KG-computed predicates
  REPLACE matching AAS init terms; uncovered predicates (StationAt, Free, On,
  etc.) are kept from the AAS init as-is.

Usage (called from context.py):
    kg_init = collect_init_from_kg(
        aas_iri_to_pddl_name, query_endpoint, abox_graph, tbox_graph, timeout,
        views_dir=Path(".../kg-bridge/sparql/views")
    )
    merged = merge_init(aas_init_terms, kg_init)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import requests

logger = logging.getLogger(__name__)

# Predicates covered by KG views — we own their init values; AAS terms for
# these predicates are removed and replaced with KG-live values.
_KG_OWNED_PREDICATES: Set[str] = {
    "Operational",
    "Occupied",
    "InRange",
    "ResourceAt",
    "ProductAt",
}

APEX = "https://w3id.org/2026/apex/"


def collect_init_from_kg(
    aas_iri_to_pddl_name: Dict[str, str],
    query_endpoint: str,
    abox_graph: str,
    tbox_graph: str,
    timeout_seconds: float = 10.0,
    views_dir: Optional[Path] = None,
) -> List[dict]:
    """Return init term-tree atoms from live KG predicate views.

    aas_iri_to_pddl_name: {aas_iri: pddl_object_name} — built from Problem.Objects.
    views_dir: path to the kg-bridge sparql/views directory.  When None, the
               views are inlined (uses the SELECT fallback path).
    """
    if views_dir is None:
        views_dir = _default_views_dir()

    # Build product-level mapping too (products have arsox:hasAASForProduct links).
    # We resolve resource/product IRIs to PDDL names on demand (cached).
    name_resolver = _NameResolver(aas_iri_to_pddl_name, query_endpoint, abox_graph, timeout_seconds)

    init_terms: List[dict] = []

    for view_name, predicate_key, arg_extractor in _VIEW_SPECS:
        view_file = views_dir / f"{view_name}.rq"
        query = _load_and_patch_view(view_file, abox_graph, tbox_graph)
        if not query:
            continue
        try:
            turtle = _run_construct(query, query_endpoint, timeout_seconds)
        except Exception as exc:
            logger.warning("View %s failed: %s", view_name, exc)
            continue
        terms = arg_extractor(turtle, name_resolver, predicate_key)
        init_terms.extend(terms)
        if terms:
            logger.debug("View %s → %d init term(s)", view_name, len(terms))

    logger.info("KG-derived init: %d term(s) across %d view(s)", len(init_terms), len(_VIEW_SPECS))
    return init_terms


def merge_init(
    aas_init_terms: List[dict],
    kg_init_terms: List[dict],
) -> List[dict]:
    """Merge AAS init terms with KG-live init terms.

    KG owns the predicates in _KG_OWNED_PREDICATES; AAS terms for those are
    dropped and replaced with the KG values.  All other AAS terms are kept.
    """
    if not kg_init_terms:
        return list(aas_init_terms)

    kg_fluent_keys = {_fluent_key(t) for t in kg_init_terms}
    kg_owned = _KG_OWNED_PREDICATES | kg_fluent_keys

    merged: List[dict] = []
    for term in aas_init_terms:
        fkey = _fluent_key(term)
        if fkey not in kg_owned:
            merged.append(term)

    merged.extend(kg_init_terms)
    return merged


# ── Internal helpers ─────────────────────────────────────────────────────────

def _fluent_key(term: dict) -> str:
    if term.get("kind") == "atom":
        return str(term.get("fluent") or "")
    return ""


def _default_views_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "kg-bridge" / "sparql" / "views"


def _load_and_patch_view(view_file: Path, abox_graph: str, tbox_graph: str) -> Optional[str]:
    if not view_file.exists():
        logger.warning("View file not found: %s", view_file)
        return None
    text = view_file.read_text(encoding="utf-8")
    # SPARQL shorthand `aas:Submodel/submodelElements` is not valid in all parsers.
    text = text.replace(
        "aas:Submodel/submodelElements",
        "<https://admin-shell.io/aas/3/1/Submodel/submodelElements>",
    )
    # Patch FROM clauses to use runtime graph IRIs.
    text = text.replace("FROM <urn:kg:tbox>", f"FROM <{tbox_graph}>")
    text = text.replace("FROM <urn:kg:abox>", f"FROM <{abox_graph}>")
    return text


def _run_construct(query: str, endpoint: str, timeout: float) -> str:
    resp = requests.post(
        endpoint,
        data={"query": query},
        headers={"Accept": "text/turtle"},
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.text


# ── Name resolver ─────────────────────────────────────────────────────────────

class _NameResolver:
    """Resolve predicate argument IRIs (AAS IRIs) to PDDL object names.

    With the ResourceAssetAdministrationShell / ProductAssetAdministrationShell
    redesign, predicate fact arguments are AAS IRIs directly — no intermediate
    synthetic entity node.  Resolution is therefore a direct dict lookup.
    """

    def __init__(
        self,
        aas_iri_to_pddl_name: Dict[str, str],
        query_endpoint: str,
        abox_graph: str,
        timeout: float,
    ) -> None:
        self._name_map = dict(aas_iri_to_pddl_name)
        self._cache: Dict[str, Optional[str]] = {}
        # Keep these for potential future use / fallback
        self._query_endpoint = query_endpoint
        self._abox_graph = abox_graph
        self._timeout = timeout

    def resolve(self, entity_iri: str) -> Optional[str]:
        """Resolve an AAS IRI → PDDL object name."""
        if entity_iri in self._name_map:
            return self._name_map[entity_iri]
        if entity_iri in self._cache:
            return self._cache[entity_iri]
        # Predicate arguments are now AAS IRIs; no entity-node hop needed.
        result = None
        self._cache[entity_iri] = result
        return result


# ── Argument extractors ───────────────────────────────────────────────────────

def _extract_unary(turtle: str, resolver: _NameResolver, fluent_key: str) -> List[dict]:
    """Extract unary predicate facts: (resource,)."""
    import rdflib
    g = rdflib.Graph()
    try:
        g.parse(data=turtle, format="turtle")
    except Exception as exc:
        logger.warning("Failed to parse %s turtle: %s", fluent_key, exc)
        return []

    APEX_NS = rdflib.Namespace(APEX)
    pred_class = APEX_NS[fluent_key]
    arb_pred = APEX_NS["hasArgumentBinding"]
    arg_obj = APEX_NS["argumentObject"]

    terms: List[dict] = []
    for fact in g.subjects(rdflib.RDF.type, pred_class):
        for arg in g.objects(fact, arb_pred):
            entity = g.value(arg, arg_obj)
            if entity:
                name = resolver.resolve(str(entity))
                if name:
                    terms.append(_atom(fluent_key, name))
    return terms


def _extract_binary_obj_lit(
    turtle: str, resolver: _NameResolver, fluent_key: str
) -> List[dict]:
    """Extract binary predicate facts where arg1=resource (object) and arg2=literal."""
    import rdflib
    g = rdflib.Graph()
    try:
        g.parse(data=turtle, format="turtle")
    except Exception as exc:
        logger.warning("Failed to parse %s turtle: %s", fluent_key, exc)
        return []

    APEX_NS = rdflib.Namespace(APEX)
    pred_class = APEX_NS[fluent_key]
    arb_pred = APEX_NS["hasArgumentBinding"]
    arg_idx = APEX_NS["argumentIndex"]
    arg_obj = APEX_NS["argumentObject"]
    arg_lit = APEX_NS["argumentLiteral"]

    terms: List[dict] = []
    for fact in g.subjects(rdflib.RDF.type, pred_class):
        args_by_idx: Dict[int, Tuple[Optional[str], Optional[str]]] = {}
        for arg in g.objects(fact, arb_pred):
            idx_node = g.value(arg, arg_idx)
            if idx_node is None:
                continue
            idx = int(str(idx_node))
            obj = g.value(arg, arg_obj)
            lit = g.value(arg, arg_lit)
            args_by_idx[idx] = (str(obj) if obj else None, str(lit) if lit else None)

        if 1 not in args_by_idx or 2 not in args_by_idx:
            continue

        obj_iri, _ = args_by_idx[1]
        _, lit_val = args_by_idx[2]
        if obj_iri is None or lit_val is None:
            continue

        name = resolver.resolve(obj_iri)
        if name:
            terms.append(_atom(fluent_key, name, lit_val))
    return terms


def _extract_binary_obj_obj(
    turtle: str, resolver: _NameResolver, fluent_key: str
) -> List[dict]:
    """Extract binary predicate facts where both arguments are objects (resources)."""
    import rdflib
    g = rdflib.Graph()
    try:
        g.parse(data=turtle, format="turtle")
    except Exception as exc:
        logger.warning("Failed to parse %s turtle: %s", fluent_key, exc)
        return []

    APEX_NS = rdflib.Namespace(APEX)
    pred_class = APEX_NS[fluent_key]
    arb_pred = APEX_NS["hasArgumentBinding"]
    arg_idx = APEX_NS["argumentIndex"]
    arg_obj = APEX_NS["argumentObject"]

    terms: List[dict] = []
    for fact in g.subjects(rdflib.RDF.type, pred_class):
        args_by_idx: Dict[int, str] = {}
        for arg in g.objects(fact, arb_pred):
            idx_node = g.value(arg, arg_idx)
            obj = g.value(arg, arg_obj)
            if idx_node is not None and obj is not None:
                args_by_idx[int(str(idx_node))] = str(obj)

        names = []
        for idx in sorted(args_by_idx):
            name = resolver.resolve(args_by_idx[idx])
            if name is None:
                break
            names.append(name)
        else:
            if len(names) == 2:
                terms.append(_atom(fluent_key, *names))
    return terms


# ── View specifications ───────────────────────────────────────────────────────
# (view_file_name, pddl_fluent_key, extractor_function)

_VIEW_SPECS = [
    ("operational",  "Operational",  _extract_unary),
    ("occupied",     "Occupied",     _extract_unary),
    ("resource-at",  "ResourceAt",   _extract_binary_obj_lit),
    ("product-at",   "ProductAt",    _extract_binary_obj_lit),
    ("in-range",     "InRange",      _extract_binary_obj_obj),
]


def _atom(fluent: str, *args: str) -> dict:
    return {
        "kind": "atom",
        "fluent": fluent,
        "params": [{"kind": "object", "name": a} for a in args],
    }
