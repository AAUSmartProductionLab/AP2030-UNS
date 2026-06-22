"""Regenerate shacl/generated/shapes.generated.shacl.ttl from ARSO_AAS.ttl.

Applies the owl2sh-semi-closed ruleset to the union of ARSO_AAS.ttl and the
locally-vendored AAS v3.1 ontology. The catalog at ontology/catalog-v001.xml
documents the URL->file mapping; we mirror it inline here so rdflib resolves
`owl:imports <https://admin-shell.io/aas/3/1/>` without a network call.
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from rdflib import Graph, OWL

from generate_shapes_from_ontology import import_uri_to_local_path, run_owl2shacl_rules


_WORKSPACE     = Path(__file__).resolve().parents[1]
_ONTOLOGY_DIR  = _WORKSPACE / "ontology"
_MODULES_DIR   = _ONTOLOGY_DIR / "modules"
_ARSO_AAS_TTL  = _ONTOLOGY_DIR / "ARSO_AAS.ttl"
_AAS_RDF_TTL   = _ONTOLOGY_DIR / "aas-rdf-ontology.ttl"
_CSS_TTL       = _ONTOLOGY_DIR / "CSS-Ontology.ttl"
_RULESET       = _ONTOLOGY_DIR / "owl2shacl" / "owl2sh-semi-closed.ttl"
_OUTPUT        = _WORKSPACE / "shacl" / "generated" / "shapes.generated.shacl.ttl"


# URL -> local file. Mirror of ontology/catalog-v001.xml entries.
_IMPORT_CATALOG: dict[str, Path] = {
    # AAS v3.1 ontology
    "https://admin-shell.io/aas/3/1/": _AAS_RDF_TTL,
    "https://admin-shell.io/aas/3/1":  _AAS_RDF_TTL,
    "http://admin-shell.io/aas/3/1/":  _AAS_RDF_TTL,
    # CSS ontology
    "http://www.w3id.org/hsu-aut/css":  _CSS_TTL,
    "http://www.w3id.org/hsu-aut/css/": _CSS_TTL,
    # ARSO modules
    "https://w3id.org/2025/arso/modules/nameplate":               _MODULES_DIR / "nameplate.ttl",
    "https://w3id.org/2025/arso/modules/hierarchical-structures": _MODULES_DIR / "hierarchical_structures.ttl",
    "https://w3id.org/2025/arso/modules/aid":                     _MODULES_DIR / "aid.ttl",
    "https://w3id.org/2025/arso/modules/skills":                  _MODULES_DIR / "skills.ttl",
    "https://w3id.org/2025/arso/modules/capabilities":            _MODULES_DIR / "capabilities.ttl",
    "https://w3id.org/2025/arso/modules/operational-data":        _MODULES_DIR / "operational_data.ttl",
    "https://w3id.org/2025/arso/modules/parameters":              _MODULES_DIR / "parameters.ttl",
}


def _resolve_with_catalog(import_uri: str, parent_file: Path) -> Path | None:
    canon = import_uri.rstrip("/")
    if import_uri in _IMPORT_CATALOG:
        return _IMPORT_CATALOG[import_uri]
    if canon in _IMPORT_CATALOG:
        return _IMPORT_CATALOG[canon]
    return import_uri_to_local_path(import_uri, parent_file)


def _load_with_imports(target: Graph, ontology_file: Path, visited: set[Path]) -> None:
    resolved = ontology_file.resolve()
    if resolved in visited or not resolved.exists():
        return
    visited.add(resolved)
    g = Graph().parse(str(resolved), format="turtle")
    target += g
    for _, _, imported in g.triples((None, OWL.imports, None)):
        local = _resolve_with_catalog(str(imported), resolved)
        if local is not None:
            _load_with_imports(target, local, visited)


def main() -> None:
    for required in (_ARSO_AAS_TTL, _AAS_RDF_TTL, _CSS_TTL, _RULESET):
        if not required.exists():
            raise FileNotFoundError(f"Required file not found: {required}")

    ontology_graph = Graph()
    visited: set[Path] = set()
    _load_with_imports(ontology_graph, _ARSO_AAS_TTL, visited)
    if _AAS_RDF_TTL.resolve() not in visited:
        _load_with_imports(ontology_graph, _AAS_RDF_TTL, visited)

    rules_graph = Graph().parse(str(_RULESET), format="turtle")
    generated_shapes = run_owl2shacl_rules(ontology_graph, rules_graph)

    _OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    generated_shapes.serialize(destination=str(_OUTPUT), format="turtle")
    print(f"Generated v2 shapes from ARSO_AAS.ttl: {_OUTPUT}")
    print(f"Triples in shape graph: {len(generated_shapes)}")


if __name__ == "__main__":
    main()
