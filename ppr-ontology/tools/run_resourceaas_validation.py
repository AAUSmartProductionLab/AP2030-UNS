import argparse
from pathlib import Path
from urllib.parse import urlparse
from typing import Any

from pyshacl import validate
from rdflib import Graph, OWL, Namespace, RDF

try:
    # Package import path (used by API/generation modules).
    from .mock_resourceaas_to_rdf import convert
    from .validate_with_basyx import validate_json_with_basyx
except ImportError:
    # Fallback when running this file directly as a script.
    from mock_resourceaas_to_rdf import convert
    from validate_with_basyx import validate_json_with_basyx


def _resolve_combined_shapes(shape_paths: list[Path]) -> list[Path]:
    ordered: list[Path] = []
    seen: set[Path] = set()

    def add_if_exists(path: Path) -> None:
        resolved = path.resolve()
        if resolved.exists() and resolved not in seen:
            seen.add(resolved)
            ordered.append(resolved)

    for path in shape_paths:
        add_if_exists(path)

    generated_name = "shapes.generated.shacl.ttl"
    has_manual = any(path.name == "shapes.sparql.manual.shacl.ttl" for path in ordered)

    if not has_manual:
        for path in list(ordered):
            if path.name != generated_name:
                continue

            candidate_manual_source = path.parents[1] / "manual" / "resourceaas-sparql-rules.shacl.ttl"
            add_if_exists(candidate_manual_source)

    return ordered


def _import_uri_to_local_path(import_uri: str, parent_file: Path) -> Path | None:
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


def _load_ontology_with_imports(data_graph: Graph, ontology_file: Path, visited: set[Path]) -> None:
    resolved_file = ontology_file.resolve()
    if resolved_file in visited or not resolved_file.exists():
        return

    visited.add(resolved_file)
    temp_graph = Graph().parse(str(resolved_file), format="turtle")
    data_graph += temp_graph

    for _, _, imported in temp_graph.triples((None, OWL.imports, None)):
        imported_path = _import_uri_to_local_path(str(imported), resolved_file)
        if imported_path is not None:
            _load_ontology_with_imports(data_graph, imported_path, visited)


def run_validation(
    input_json: Path,
    generated_rdf: Path,
    report_ttl: Path,
    shapes_paths: list[Path],
    ontology_paths: list[Path],
) -> tuple[bool, str]:
    result = run_validation_detailed(
        input_json=input_json,
        generated_rdf=generated_rdf,
        report_ttl=report_ttl,
        shapes_paths=shapes_paths,
        ontology_paths=ontology_paths,
    )
    return bool(result["conforms"]), str(result["report_text"])


def _extract_shacl_issues(report_graph: Graph) -> list[dict[str, str]]:
    sh = Namespace("http://www.w3.org/ns/shacl#")
    severity_map = {
        str(sh.Violation): "Violation",
        str(sh.Warning): "Warning",
        str(sh.Info): "Info",
    }

    issues: list[dict[str, str]] = []
    for validation_result in report_graph.subjects(RDF.type, sh.ValidationResult):
        message = str(report_graph.value(validation_result, sh.resultMessage) or "No message")
        severity_uri = str(report_graph.value(validation_result, sh.resultSeverity) or str(sh.Violation))
        issues.append(
            {
                "source": "ontology",
                "severity": severity_map.get(severity_uri, "Violation"),
                "message": message,
            }
        )

    return issues


def _format_report_text(result: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("Validation Summary")
    lines.append(f"Overall conforms: {result['conforms']}")
    lines.append(f"Metamodel conforms: {result['metamodel_conforms']}")
    lines.append(f"Ontology conforms: {result['ontology_conforms']}")
    lines.append("")

    lines.append("Metamodel Validation Issues")
    metamodel_issues = result["metamodel_issues"]
    if metamodel_issues:
        for issue in metamodel_issues:
            lines.append(f"- [{issue.get('severity','Violation')}] {issue.get('message','')}")
    else:
        lines.append("- None")
    lines.append("")

    lines.append("Ontology Validation Issues")
    ontology_issues = result["ontology_issues"]
    if ontology_issues:
        for issue in ontology_issues:
            lines.append(f"- [{issue.get('severity','Violation')}] {issue.get('message','')}")
    else:
        lines.append("- None")

    return "\n".join(lines)


def run_validation_detailed(
    input_json: Path,
    generated_rdf: Path,
    report_ttl: Path,
    shapes_paths: list[Path],
    ontology_paths: list[Path],
) -> dict[str, Any]:
    basyx_result = validate_json_with_basyx(input_json)
    metamodel_issues: list[dict[str, str]] = list(basyx_result.get("issues", []))
    metamodel_warnings: list[dict[str, str]] = list(basyx_result.get("warnings", []))
    metamodel_conforms = bool(basyx_result.get("conforms", False))

    convert(input_json, generated_rdf)

    data_graph = Graph().parse(str(generated_rdf), format="turtle")
    visited_ontologies: set[Path] = set()
    for ontology_file in ontology_paths:
        _load_ontology_with_imports(data_graph, ontology_file, visited_ontologies)

    resolved_shapes = _resolve_combined_shapes(shapes_paths)
    if not resolved_shapes:
        raise FileNotFoundError("No SHACL shape files could be resolved for validation.")

    shapes_graph = Graph()
    for shape_file in resolved_shapes:
        shapes_graph.parse(str(shape_file), format="turtle")

    ontology_conforms, report_graph, report_text = validate(
        data_graph,
        shacl_graph=shapes_graph,
        inference="rdfs",
        abort_on_first=False,
        allow_infos=True,
        allow_warnings=True,
        meta_shacl=False,
        advanced=True,
        debug=False,
    )

    report_ttl.parent.mkdir(parents=True, exist_ok=True)
    if hasattr(report_graph, "serialize"):
        report_graph.serialize(destination=str(report_ttl), format="turtle")
    else:
        report_ttl.write_text(str(report_graph), encoding="utf-8")

    ontology_issues = _extract_shacl_issues(report_graph)
    combined_result: dict[str, Any] = {
        "conforms": bool(metamodel_conforms and ontology_conforms),
        "metamodel_conforms": bool(metamodel_conforms),
        "ontology_conforms": bool(ontology_conforms),
        "metamodel_issues": metamodel_issues,
        "metamodel_warnings": metamodel_warnings,
        "ontology_issues": ontology_issues,
        "report_text": str(report_text),
    }
    combined_result["summary_text"] = _format_report_text(combined_result)
    return combined_result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run SHACL validation for ResourceAAS mock input.")
    parser.add_argument("--input", required=True,
                        help="Path to ResourceAAS JSON input.")
    parser.add_argument(
        "--generated-rdf",
        default="validation/outputs/generated-resourceaas.ttl",
        help="Path to generated RDF Turtle.",
    )
    parser.add_argument(
        "--report",
        default="validation/outputs/resourceaas-report.ttl",
        help="Path to SHACL report Turtle.",
    )
    parser.add_argument(
        "--shapes",
        nargs="+",
        default=[
            "shacl/generated/shapes.generated.shacl.ttl",
            "shacl/manual/resourceaas-sparql-rules.shacl.ttl",
        ],
        help="One or more SHACL shape files.",
    )
    parser.add_argument(
        "--ontologies",
        nargs="+",
        default=[
            "ontology/CSS-Ontology.ttl",
            "ontology/CSSx.ttl",
        ],
        help="Ontology files loaded into the validation data graph.",
    )
    arguments = parser.parse_args()

    details = run_validation_detailed(
        Path(arguments.input),
        Path(arguments.generated_rdf),
        Path(arguments.report),
        [Path(item) for item in arguments.shapes],
        [Path(item) for item in arguments.ontologies],
    )

    print("Conforms:", details["conforms"])
    print("Metamodel conforms:", details["metamodel_conforms"])
    print("Ontology conforms:", details["ontology_conforms"])
    print(details["summary_text"])


if __name__ == "__main__":
    main()
