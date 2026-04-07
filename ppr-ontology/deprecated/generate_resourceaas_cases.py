import argparse
import copy
import json
from pathlib import Path


def remove_submodel(document: dict, submodel_suffix: str) -> None:
    shell = document["assetAdministrationShells"][0]
    suffix = f"/{submodel_suffix}"

    shell["submodels"] = [
        ref
        for ref in shell.get("submodels", [])
        if not (ref.get("keys") and str(ref["keys"][-1].get("value", "")).endswith(suffix))
    ]

    document["submodels"] = [
        submodel
        for submodel in document.get("submodels", [])
        if not str(submodel.get("id", "")).endswith(suffix)
    ]


def write_case(output_dir: Path, name: str, payload: dict) -> None:
    output_path = output_dir / f"{name}.json"
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def generate_cases(input_json: Path, output_dir: Path) -> None:
    source = json.loads(input_json.read_text(encoding="utf-8"))
    output_dir.mkdir(parents=True, exist_ok=True)

    write_case(output_dir, "valid_resourceaas", copy.deepcopy(source))

    case = copy.deepcopy(source)
    remove_submodel(case, "AID")
    write_case(output_dir, "missing_aid", case)

    case = copy.deepcopy(source)
    remove_submodel(case, "Capabilities")
    write_case(output_dir, "missing_capabilities", case)

    case = copy.deepcopy(source)
    remove_submodel(case, "Skills")
    write_case(output_dir, "missing_skills", case)

    case = copy.deepcopy(source)
    remove_submodel(case, "Nameplate")
    write_case(output_dir, "missing_nameplate", case)

    case = copy.deepcopy(source)
    remove_submodel(case, "HierarchicalStructures")
    write_case(output_dir, "missing_hierarchical_structures", case)

    case = copy.deepcopy(source)
    case["aasvTestFlags"] = {"omitCapabilitySkillRealization": True}
    write_case(output_dir, "broken_capability_skill_link", case)

    case = copy.deepcopy(source)
    case["aasvTestFlags"] = {"omitSkillInterfaceResourceInterfaceLink": True}
    write_case(output_dir, "broken_skill_interface_link", case)

    case = copy.deepcopy(source)
    case["aasvTestFlags"] = {"omitCapabilitySemanticId": True}
    write_case(output_dir, "missing_capability_semanticid", case)

    case = copy.deepcopy(source)
    case["aasvTestFlags"] = {"omitSkillSemanticId": True}
    write_case(output_dir, "missing_skill_semanticid", case)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate ResourceAAS positive/negative SHACL test cases.")
    parser.add_argument("--input", required=True, help="Path to base ResourceAAS JSON file.")
    parser.add_argument(
        "--output-dir",
        default="test/resourceaas-cases",
        help="Directory where generated test case JSON files are written.",
    )
    arguments = parser.parse_args()

    generate_cases(Path(arguments.input), Path(arguments.output_dir))


if __name__ == "__main__":
    main()
