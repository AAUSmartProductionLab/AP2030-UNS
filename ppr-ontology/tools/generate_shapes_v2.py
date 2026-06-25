"""Regenerate shacl/generated_v2/shapes.generated.shacl.ttl from CSSx_AAS.ttl.

Applies the owl2sh-semi-closed ruleset to the union of CSSx_AAS.ttl and the
locally-vendored AAS v3.1 ontology. The catalog at ontology/catalog-v001.xml
documents the URL→file mapping; we mirror it inline here so rdflib resolves
`owl:imports <https://admin-shell.io/aas/3/1/>` without a network call.
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from rdflib import Graph, OWL

from generate_shapes_from_ontology import import_uri_to_local_path, run_owl2shacl_rules


_WORKSPACE     = Path(__file__).resolve().parents[1]
_ONTOLOGY_DIR  = _WORKSPACE / "ontology"
_CSSX_AAS_TTL  = _ONTOLOGY_DIR / "CSSx_AAS.ttl"
_AAS_RDF_TTL   = _ONTOLOGY_DIR / "aas-rdf-ontology.ttl"
_RULESET       = _ONTOLOGY_DIR / "owl2shacl" / "owl2sh-semi-closed.ttl"
_OUTPUT        = _WORKSPACE / "shacl" / "generated_v2" / "shapes.generated.shacl.ttl"


# URL → local file. Mirror of ontology/catalog-v001.xml entries.
_IMPORT_CATALOG: dict[str, Path] = {
    "https://admin-shell.io/aas/3/1/": _AAS_RDF_TTL,
    "https://admin-shell.io/aas/3/1":  _AAS_RDF_TTL,
    "http://admin-shell.io/aas/3/1/":  _AAS_RDF_TTL,
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
    for required in (_CSSX_AAS_TTL, _AAS_RDF_TTL, _RULESET):
        if not required.exists():
            raise FileNotFoundError(f"Required file not found: {required}")

    ontology_graph = Graph()
    visited: set[Path] = set()
    _load_with_imports(ontology_graph, _CSSX_AAS_TTL, visited)
    if _AAS_RDF_TTL.resolve() not in visited:
        _load_with_imports(ontology_graph, _AAS_RDF_TTL, visited)

    rules_graph = Graph().parse(str(_RULESET), format="turtle")
    generated_shapes = run_owl2shacl_rules(ontology_graph, rules_graph)

    _OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    generated_shapes.serialize(destination=str(_OUTPUT), format="turtle")
    print(f"Generated v2 shapes from CSSx_AAS.ttl: {_OUTPUT}")
    print(f"Triples in shape graph: {len(generated_shapes)}")


if __name__ == "__main__":
    main()
