from pathlib import Path
from urllib.parse import urlparse

from rdflib import Graph, OWL


def import_uri_to_local_path(import_uri: str, parent_file: Path) -> Path | None:
    parsed = urlparse(import_uri)
    if parsed.scheme in ("http", "https"):
        ttl_name = Path(parsed.path).name
        if ttl_name.endswith(".ttl"):
            candidates = [
                (parent_file.parent / ttl_name).resolve(),
                (parent_file.parent / "modules" / ttl_name).resolve(),
                (parent_file.parent.parent / "modules" / ttl_name).resolve(),
            ]
            for candidate in candidates:
                if candidate.exists():
                    return candidate
        return None
    if parsed.scheme == "file":
        return Path(parsed.path)
    if parsed.scheme:
        return None
    return (parent_file.parent / import_uri).resolve()


def load_ontology_with_imports(target_graph: Graph, ontology_file: Path, visited: set[Path]) -> None:
    resolved_file = ontology_file.resolve()
    if resolved_file in visited or not resolved_file.exists():
        return

    visited.add(resolved_file)
    local_graph = Graph().parse(str(resolved_file), format="turtle")
    target_graph += local_graph

    for _, _, imported in local_graph.triples((None, OWL.imports, None)):
        imported_path = import_uri_to_local_path(str(imported), resolved_file)
        if imported_path is not None:
            load_ontology_with_imports(target_graph, imported_path, visited)


def run_owl2shacl_rules(ontology_graph: Graph, rules_graph: Graph) -> Graph:
    try:
        from pyshacl import shacl_rules
    except ImportError as exc:
        raise RuntimeError(
            "pyshacl with SHACL-AF support is required. Install project validation requirements first."
        ) from exc

    rules_result = shacl_rules(
        ontology_graph,
        shacl_graph=rules_graph,
        inference="rdfs",
        advanced=True,
        iterate_rules=True,
        inplace=False,
    )

    if isinstance(rules_result, tuple):
        for item in rules_result:
            if isinstance(item, Graph):
                return item
        raise RuntimeError("Unexpected pyshacl.shacl_rules return value: no graph produced.")

    if not isinstance(rules_result, Graph):
        raise RuntimeError("Unexpected pyshacl.shacl_rules return type.")

    return rules_result


WORKSPACE = Path(__file__).resolve().parents[1]
ONTOLOGY_FILES = [
    WORKSPACE / "ontology" / "CSS-Ontology.ttl",
    WORKSPACE / "ontology" / "CSSx.ttl",
]
OWL2SHACL_RULESET = WORKSPACE / "ontology" / "owl2shacl" / "owl2sh-semi-closed.ttl"
GENERATED_OUTPUT = WORKSPACE / "shacl" / "generated" / "shapes.generated.shacl.ttl"
MANUAL_SPARQL_INPUT = WORKSPACE / "shacl" / "manual" / "resourceaas-sparql-rules.shacl.ttl"


def main() -> None:
    for ontology_file in ONTOLOGY_FILES:
        if not ontology_file.exists():
            raise FileNotFoundError(f"Ontology file not found: {ontology_file}")

    if not OWL2SHACL_RULESET.exists():
        raise FileNotFoundError(f"OWL2SHACL ruleset not found: {OWL2SHACL_RULESET}")

    if not MANUAL_SPARQL_INPUT.exists():
        raise FileNotFoundError(f"Manual SPARQL rules file not found: {MANUAL_SPARQL_INPUT}")

    ontology_graph = Graph()
    visited: set[Path] = set()
    for ontology in ONTOLOGY_FILES:
        load_ontology_with_imports(ontology_graph, ontology, visited)

    rules_graph = Graph().parse(str(OWL2SHACL_RULESET), format="turtle")
    generated_shapes = run_owl2shacl_rules(ontology_graph, rules_graph)

    GENERATED_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    generated_shapes.serialize(destination=str(GENERATED_OUTPUT), format="turtle")

    print(f"Generated ontology-derived shapes: {GENERATED_OUTPUT}")
    print(f"Manual SPARQL rules source: {MANUAL_SPARQL_INPUT}")


if __name__ == "__main__":
    main()
