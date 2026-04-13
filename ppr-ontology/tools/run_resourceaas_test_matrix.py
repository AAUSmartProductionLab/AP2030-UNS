import argparse
from pathlib import Path

from run_resourceaas_validation import run_validation


EXPECTED_CONFORMS = {
    "valid_resourceaas": True,
    "missing_aid": False,
    "missing_capabilities": False,
    "missing_skills": False,
    "missing_nameplate": False,
    "missing_hierarchical_structures": False,
    "broken_capability_skill_link": False,
    "broken_skill_interface_link": False,
    "missing_capability_semanticid": False,
    "missing_skill_semanticid": False,
    "empty_hierarchical_bom_entries": False,
    "duplicate_nameplate_submodel": True,
}


def run_matrix(cases_dir: Path, output_dir: Path, shapes: list[Path], ontologies: list[Path]) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    failed = 0

    for case_name, expected in EXPECTED_CONFORMS.items():
        input_path = cases_dir / f"{case_name}.json"
        if not input_path.exists():
            print(f"[MISSING] {input_path}")
            failed += 1
            continue

        generated_rdf = output_dir / f"{case_name}.generated.ttl"
        report_ttl = output_dir / f"{case_name}.report.ttl"
        conforms, _ = run_validation(input_path, generated_rdf, report_ttl, shapes, ontologies)

        verdict = "PASS" if conforms == expected else "FAIL"
        print(f"[{verdict}] {case_name}: conforms={conforms}, expected={expected}")
        if verdict == "FAIL":
            failed += 1

    return failed


def main() -> None:
    parser = argparse.ArgumentParser(description="Run SHACL validation matrix for ResourceAAS test cases.")
    parser.add_argument("--cases-dir", default="validation/cases", help="Directory containing generated JSON cases.")
    parser.add_argument("--output-dir", default="validation/outputs/matrix", help="Directory for generated RDF/report files.")
    parser.add_argument(
        "--shapes",
        nargs="+",
        default=[
            "shacl/generated/shapes.generated.shacl.ttl",
            "shacl/manual/resourceaas-sparql-rules.shacl.ttl",
        ],
        help="SHACL shape files.",
    )
    parser.add_argument(
        "--ontologies",
        nargs="+",
        default=[
            "ontology/CSS-Ontology.ttl",
            "ontology/CSSx.ttl",
        ],
        help="Ontology files loaded into each validation run.",
    )
    args = parser.parse_args()

    failures = run_matrix(
        Path(args.cases_dir),
        Path(args.output_dir),
        [Path(shape) for shape in args.shapes],
        [Path(ontology) for ontology in args.ontologies],
    )
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
