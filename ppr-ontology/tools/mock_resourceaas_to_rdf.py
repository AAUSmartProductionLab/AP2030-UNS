import argparse
import json
import re
from pathlib import Path

from rdflib import Graph, Literal, Namespace, RDF, RDFS, URIRef
from rdflib.namespace import XSD


CSS = Namespace("http://www.w3id.org/hsu-aut/css#")
CSSX = Namespace("http://www.w3id.org/aau-ra/cssx#")
AASV = Namespace("http://www.w3id.org/aau-ra/resourceaas-validation#")


SUBMODEL_TYPE_BY_IDSHORT = {
    "digitalnameplate": AASV.DigitalNameplateSubmodel,
    "nameplate": AASV.DigitalNameplateSubmodel,
    "hierarchicalstructures": AASV.HierarchicalStructuresSubmodel,
    "bom": AASV.HierarchicalStructuresSubmodel,
    "billofmaterial": AASV.HierarchicalStructuresSubmodel,
    "capabilities": AASV.CapabilitiesSubmodel,
    "offeredcapabilitydescription": AASV.CapabilitiesSubmodel,
    "skills": AASV.SkillsSubmodel,
    "operationaldata": AASV.OperationalDataSubmodel,
    "aid": AASV.AIDSubmodel,
    "assetinterfacedescription": AASV.AIDSubmodel,
    "assetinterfacesdescription": AASV.AIDSubmodel,
    "parameters": AASV.ParametersSubmodel,
}


SUBMODEL_LINK_BY_TYPE = {
    AASV.DigitalNameplateSubmodel: AASV.hasDigitalNameplateSubmodel,
    AASV.HierarchicalStructuresSubmodel: AASV.hasHierarchicalStructuresSubmodel,
    AASV.CapabilitiesSubmodel: AASV.hasCapabilitiesSubmodel,
    AASV.SkillsSubmodel: AASV.hasSkillsSubmodel,
    AASV.OperationalDataSubmodel: AASV.hasOperationalDataSubmodel,
    AASV.AIDSubmodel: AASV.hasAIDSubmodel,
    AASV.ParametersSubmodel: AASV.hasParametersSubmodel,
}


def get_submodel_idshort_map(document: dict) -> dict[str, dict]:
    return {
        entry.get("id"): entry
        for entry in document.get("submodels", [])
        if entry.get("modelType") == "Submodel"
    }


def normalized_idshort(submodel: dict) -> str:
    return str(submodel.get("idShort", "")).strip().lower()


def has_type(present_submodels: set[URIRef], target_type: URIRef, graph: Graph) -> bool:
    for sm in present_submodels:
        if (sm, RDF.type, target_type) in graph:
            return True
    return False


def first_semantic_id(node: dict) -> str | None:
    semantic_id = node.get("semanticId", {})
    keys = semantic_id.get("keys", []) if isinstance(semantic_id, dict) else []
    for key in keys:
        value = key.get("value")
        if value:
            return str(value)
    return None


def semantic_ids(node: dict) -> list[str]:
    values: list[str] = []

    semantic_id = node.get("semanticId", {})
    keys = semantic_id.get("keys", []) if isinstance(semantic_id, dict) else []
    for key in keys:
        value = key.get("value")
        if value:
            values.append(str(value))

    for supplemental in node.get("supplementalSemanticIds", []):
        if not isinstance(supplemental, dict):
            continue
        keys = supplemental.get("keys", [])
        if not isinstance(keys, list):
            continue
        for key in keys:
            if not isinstance(key, dict):
                continue
            value = key.get("value")
            if value:
                values.append(str(value))

    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def first_multilang_text(element: dict) -> str | None:
    value = element.get("value", [])
    if not isinstance(value, list):
        return None
    for item in value:
        if isinstance(item, dict):
            text = item.get("text")
            if text:
                return str(text)
    return None


def first_multilang_entry(element: dict) -> tuple[str, str | None] | None:
    value = element.get("value", [])
    if not isinstance(value, list):
        return None
    for item in value:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if not text:
            continue
        language = item.get("language")
        return str(text), (str(language) if language else None)
    return None


def element_property_value(container: dict, idshort: str) -> str | None:
    for item in container.get("value", []):
        if not isinstance(item, dict):
            continue
        if item.get("idShort") == idshort and item.get("modelType") == "Property":
            value = item.get("value")
            if value not in (None, ""):
                return str(value)
    return None


def normalize_local_name(text: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return safe or "item"


def semantic_trace_path(path: str, index: int) -> str:
    return f"{path}#{index}"


def iterate_semantic_elements(elements: list, path_prefix: str = ""):
    if not isinstance(elements, list):
        return

    for index, element in enumerate(elements):
        if not isinstance(element, dict):
            continue

        idshort = str(element.get(
            "idShort", f"element-{index}")).strip() or f"element-{index}"
        current_path = f"{path_prefix}/{idshort}[{index}]" if path_prefix else f"{idshort}[{index}]"
        yield element, current_path

        value = element.get("value")
        if isinstance(value, list):
            yield from iterate_semantic_elements(value, current_path)


def add_submodel_semantic_traces(graph: Graph, resource: URIRef, submodel_uri: URIRef, submodel: dict) -> None:
    for semantic in semantic_ids(submodel):
        graph.add((submodel_uri, AASV.sourceSemanticId, Literal(semantic)))

    for element, element_path in iterate_semantic_elements(submodel.get("submodelElements", [])):
        element_semantics = semantic_ids(element)
        if not element_semantics:
            continue

        idshort = str(element.get("idShort", "")).strip()
        for index, semantic in enumerate(element_semantics):
            trace_uri = URIRef(
                f"{submodel_uri}#trace-{normalize_local_name(semantic_trace_path(element_path, index))}")
            graph.add((trace_uri, AASV.sourceSemanticId, Literal(semantic)))
            if idshort:
                graph.add((trace_uri, AASV.sourceIdShort, Literal(idshort)))
            graph.add((trace_uri, AASV.sourceElementPath, Literal(element_path)))
            graph.add((submodel_uri, AASV.hasMappedElement, trace_uri))
            graph.add((resource, AASV.hasMappedElement, trace_uri))


def find_submodel_by_type(present_submodels: set[URIRef], target_type: URIRef, graph: Graph) -> URIRef | None:
    for sm in present_submodels:
        if (sm, RDF.type, target_type) in graph:
            return sm
    return None


def get_submodel_idshort(document: dict, submodel_uri: URIRef) -> dict | None:
    submodel_id = str(submodel_uri)
    for submodel in document.get("submodels", []):
        if submodel.get("id") == submodel_id:
            return submodel
    return None


def add_nameplate_mapping(graph: Graph, resource: URIRef, nameplate_submodel: dict) -> None:
    manufacturer = URIRef(f"{resource}#manufacturer")
    has_manufacturer = False

    idshort_to_property = {
        "URIOfTheProduct": (CSSX.uriOfTheProduct, None),
        "ManufacturerProductDesignation": (CSSX.manufacturerProductDesignation, None),
        "ManufacturerProductFamily": (CSSX.manufacturerProductFamily, None),
        "ManufacturerArticleNumber": (CSSX.productArticleNumberOfManufacturer, None),
        "SerialNumber": (CSSX.serialNumber, None),
        "YearOfConstruction": (CSSX.yearOfConstruction, None),
        "DateOfManufacture": (CSSX.dateOfManufacture, None),
        "HardwareVersion": (CSSX.hardwareVersion, None),
        "SoftwareVersion": (CSSX.softwareVersion, None),
    }

    for element in nameplate_submodel.get("submodelElements", []):
        if not isinstance(element, dict):
            continue
        idshort = element.get("idShort")
        model_type = element.get("modelType")

        if idshort == "ManufacturerName" and model_type == "MultiLanguageProperty":
            manufacturer_name_entry = first_multilang_entry(element)
            if manufacturer_name_entry:
                manufacturer_name, language = manufacturer_name_entry
                graph.add((manufacturer, RDF.type, CSSX.Manufacturer))
                if language:
                    graph.add((manufacturer, CSSX.manufacturerName,
                              Literal(manufacturer_name, lang=language)))
                else:
                    graph.add((manufacturer, CSSX.manufacturerName,
                              Literal(manufacturer_name)))
                has_manufacturer = True
                semantic = first_semantic_id(element)
                if semantic:
                    graph.add(
                        (manufacturer, AASV.sourceSemanticId, Literal(semantic)))
            continue

        mapped = idshort_to_property.get(idshort)
        if not mapped:
            continue

        predicate, _ = mapped
        if model_type == "Property":
            value = element.get("value")
            if value not in (None, ""):
                value_str = str(value)
                if predicate == CSSX.yearOfConstruction:
                    graph.add((resource, predicate, Literal(value_str)))
                elif predicate == CSSX.dateOfManufacture:
                    graph.add((resource, predicate, Literal(value_str, datatype=XSD.date)))
                elif predicate == CSSX.uriOfTheProduct:
                    graph.add((resource, predicate, Literal(value_str, datatype=XSD.anyURI)))
                else:
                    graph.add((resource, predicate, Literal(value_str)))
        elif model_type == "MultiLanguageProperty":
            entry = first_multilang_entry(element)
            if entry:
                text, language = entry
                if language and predicate in {CSSX.manufacturerProductDesignation, CSSX.manufacturerProductFamily}:
                    graph.add((resource, predicate, Literal(text, lang=language)))
                else:
                    graph.add((resource, predicate, Literal(text)))

        semantic = first_semantic_id(element)
        if semantic:
            trace_node = URIRef(
                f"{resource}#nameplate-{normalize_local_name(idshort)}")
            graph.add((trace_node, AASV.sourceSemanticId, Literal(semantic)))
            graph.add((trace_node, AASV.sourceIdShort, Literal(str(idshort))))
            graph.add((resource, AASV.hasMappedElement, trace_node))

    if has_manufacturer:
        graph.add((resource, CSSX.hasManufacturer, manufacturer))


def extract_capabilities(graph: Graph, resource: URIRef, capabilities_submodel: dict, test_flags: dict) -> dict[str, URIRef]:
    capability_by_idshort: dict[str, URIRef] = {}
    omit_semantic = bool(test_flags.get("omitCapabilitySemanticId", False))

    top_level = capabilities_submodel.get("submodelElements", [])
    capability_elements: list[dict] = []

    for element in top_level:
        if not isinstance(element, dict):
            continue
        if element.get("modelType") != "SubmodelElementCollection":
            continue
        # Support generated layout where capabilities are nested in CapabilitySet
        if element.get("idShort") == "CapabilitySet":
            for nested in element.get("value", []):
                if isinstance(nested, dict) and nested.get("modelType") == "SubmodelElementCollection":
                    capability_elements.append(nested)
            continue
        # Support legacy flat layout with capability containers at top-level
        capability_elements.append(element)

    for element in capability_elements:
        if not isinstance(element, dict):
            continue
        if element.get("modelType") != "SubmodelElementCollection":
            continue

        cap_idshort = str(element.get("idShort", "")).strip()
        if not cap_idshort:
            continue

        cap_uri = URIRef(
            f"{resource}#capability-{normalize_local_name(cap_idshort)}")
        capability_by_idshort[cap_idshort] = cap_uri
        graph.add((cap_uri, RDF.type, CSS.Capability))
        graph.add((resource, CSS.providesCapability, cap_uri))
        graph.add((cap_uri, AASV.sourceIdShort, Literal(cap_idshort)))

        semantic_from_property = element_property_value(element, "SemanticId")
        if semantic_from_property and not omit_semantic:
            graph.add((cap_uri, AASV.sourceSemanticId,
                      Literal(semantic_from_property)))

        display_name = None
        for child in element.get("value", []):
            if isinstance(child, dict) and child.get("idShort") == "DisplayName":
                display_name = first_multilang_text(child)
                break
        if display_name:
            graph.add((cap_uri, RDFS.label, Literal(display_name)))

        semantic = first_semantic_id(element)
        if semantic:
            graph.add((cap_uri, AASV.sourceSubmodelSemanticId, Literal(semantic)))

    return capability_by_idshort


def extract_skills(graph: Graph, resource: URIRef, skills_submodel: dict, software_interface: URIRef | None, test_flags: dict) -> dict[str, URIRef]:
    skill_by_idshort: dict[str, URIRef] = {}
    omit_semantic = bool(test_flags.get("omitSkillSemanticId", False))

    for element in skills_submodel.get("submodelElements", []):
        if not isinstance(element, dict):
            continue
        if element.get("modelType") != "SubmodelElementCollection":
            continue

        skill_idshort = str(element.get("idShort", "")).strip()
        if not skill_idshort:
            continue

        skill_uri = URIRef(
            f"{resource}#skill-{normalize_local_name(skill_idshort)}")
        skill_by_idshort[skill_idshort] = skill_uri
        graph.add((skill_uri, RDF.type, CSS.Skill))
        graph.add((resource, CSS.providesSkill, skill_uri))
        graph.add((skill_uri, AASV.sourceIdShort, Literal(skill_idshort)))

        semantic_from_property = element_property_value(element, "SemanticId")
        if semantic_from_property and not omit_semantic:
            graph.add((skill_uri, AASV.sourceSemanticId,
                      Literal(semantic_from_property)))

        display_name = None
        for child in element.get("value", []):
            if isinstance(child, dict) and child.get("idShort") == "DisplayName":
                display_name = first_multilang_text(child)
                break
        if display_name:
            graph.add((skill_uri, RDFS.label, Literal(display_name)))

        skill_interface = URIRef(
            f"{resource}#skill-interface-{normalize_local_name(skill_idshort)}")
        graph.add((skill_interface, RDF.type, CSS.SkillInterface))
        graph.add((skill_uri, CSS.accessibleThrough, skill_interface))

        omit_link = bool(test_flags.get(
            "omitSkillInterfaceResourceInterfaceLink", False))
        if software_interface is not None and not omit_link:
            graph.add(
                (skill_interface, CSSX.skillInterfaceUsesSoftwareInterface, software_interface))

        semantic = first_semantic_id(element)
        if semantic:
            graph.add(
                (skill_uri, AASV.sourceSubmodelSemanticId, Literal(semantic)))

    return skill_by_idshort


def _add_bom_mapping(graph: Graph, bom_submodel_uri: URIRef, bom_submodel: dict) -> list[URIRef]:
    """Extract BoM-specific RDF so resourceaas-bom.shacl.ttl constraints can fire."""
    # Name from displayName (list of lang-string dicts)
    for item in bom_submodel.get("displayName", []):
        if isinstance(item, dict) and item.get("text"):
            graph.add((bom_submodel_uri, AASV.bomName, Literal(item["text"])))
            break

    archetype: str | None = None
    for element in bom_submodel.get("submodelElements", []):
        if not isinstance(element, dict):
            continue
        if element.get("idShort") == "ArcheType" and element.get("modelType") == "Property":
            archetype = element.get("value")
            if archetype:
                graph.add((bom_submodel_uri, AASV.bomArchetype, Literal(archetype)))
            break

    # Project entity entries from the EntryNode statements.
    # Match by semantic ID so the EntryNode idShort can be the asset name.
    _ENTRY_NODE_SEMANTIC = "https://admin-shell.io/idta/HierarchicalStructures/EntryNode/1/0"
    entry_uris: list[URIRef] = []
    for element in bom_submodel.get("submodelElements", []):
        if not isinstance(element, dict):
            continue
        if element.get("modelType") != "Entity":
            continue
        # Accept if semantic ID matches OR if idShort is "EntryNode" (backward compat)
        if first_semantic_id(element) != _ENTRY_NODE_SEMANTIC and element.get("idShort") != "EntryNode":
            continue
        for stmt in element.get("statements", []):
            if not isinstance(stmt, dict) or stmt.get("modelType") != "Entity":
                continue
            entity_name = str(stmt.get("idShort", "")).strip()
            if not entity_name:
                continue
            global_asset_id = stmt.get("globalAssetId")
            safe = re.sub(r"[^a-z0-9]+", "-", entity_name.lower()).strip("-") or "entry"
            entry_uri = URIRef(f"{bom_submodel_uri}#bom-entry-{safe}")
            entry_uris.append(entry_uri)
            graph.add((bom_submodel_uri, AASV.hasBomEntry, entry_uri))
            graph.add((entry_uri, RDF.type, AASV.BomEntry))
            graph.add((entry_uri, RDF.type, CSSX.ResourceBoMItem))
            graph.add((entry_uri, AASV.bomEntryName, Literal(entity_name)))
            graph.add((entry_uri, CSSX.itemNumber, Literal(entity_name)))
            if global_asset_id:
                graph.add((entry_uri, AASV.bomEntryGlobalAssetId, Literal(str(global_asset_id))))
        break  # only process first EntryNode

    return entry_uris


def _link_capabilities_to_skills(
    graph: Graph,
    capability_by_idshort: dict[str, URIRef],
    skill_by_idshort: dict[str, URIRef],
    omit_capability_skill_realization: bool,
) -> None:
    if omit_capability_skill_realization:
        return

    for capability_idshort, capability_uri in capability_by_idshort.items():
        cap_norm = capability_idshort.lower().replace("capability", "")
        cap_norm = re.sub(r"[^a-z0-9]+", "", cap_norm)
        if not cap_norm:
            continue

        linked = False
        for skill_idshort, skill_uri in skill_by_idshort.items():
            skill_norm = skill_idshort.lower().replace("skill", "")
            skill_norm = re.sub(r"[^a-z0-9]+", "", skill_norm)
            if not skill_norm:
                continue

            if cap_norm.startswith(skill_norm) or skill_norm.startswith(cap_norm):
                graph.add((capability_uri, CSS.isRealizedBySkill, skill_uri))
                linked = True

        if not linked:
            for skill_uri in skill_by_idshort.values():
                graph.add((capability_uri, CSS.isRealizedBySkill, skill_uri))


def convert(aas_json: Path, output_ttl: Path) -> None:
    with aas_json.open("r", encoding="utf-8") as file_handle:
        document = json.load(file_handle)

    shells = document.get("assetAdministrationShells", [])
    if not shells:
        raise ValueError("No assetAdministrationShells found in input JSON.")

    shell = shells[0]
    test_flags = document.get("aasvTestFlags", {})
    shell_id = shell.get("id")
    if not shell_id:
        raise ValueError("AAS root object is missing 'id'.")

    graph = Graph()
    graph.bind("css", CSS)
    graph.bind("cssx", CSSX)
    graph.bind("aasv", AASV)

    resource = URIRef(shell_id)
    graph.add((resource, RDF.type, CSS.Resource))
    graph.add((resource, AASV.sourceIdShort, Literal(shell.get("idShort", ""))))

    submodels_by_id = get_submodel_idshort_map(document)
    present_submodels: set[URIRef] = set()

    for model_reference in shell.get("submodels", []):
        keys = model_reference.get("keys", [])
        if not keys:
            continue

        submodel_id = keys[-1].get("value")
        if not submodel_id:
            continue

        submodel = submodels_by_id.get(submodel_id)
        if not submodel:
            continue

        submodel_uri = URIRef(submodel_id)
        present_submodels.add(submodel_uri)
        graph.add((resource, AASV.hasSubmodel, submodel_uri))

        idshort = normalized_idshort(submodel)
        graph.add((submodel_uri, AASV.hasIdShort,
                  Literal(submodel.get("idShort", ""))))

        submodel_type = SUBMODEL_TYPE_BY_IDSHORT.get(idshort)
        if submodel_type:
            graph.add((submodel_uri, RDF.type, submodel_type))
            submodel_link = SUBMODEL_LINK_BY_TYPE.get(submodel_type)
            if submodel_link:
                graph.add((resource, submodel_link, submodel_uri))

        add_submodel_semantic_traces(graph, resource, submodel_uri, submodel)

    software_interface: URIRef | None = URIRef(
        f"{shell_id}#resource-software-interface-1")

    bom_submodel_uri = find_submodel_by_type(present_submodels, AASV.HierarchicalStructuresSubmodel, graph)
    if bom_submodel_uri is not None:
        resource_bom = URIRef(f"{shell_id}#resource-bom-1")
        graph.add((resource_bom, RDF.type, CSSX.ResourceBoM))
        graph.add((resource, CSSX.hasResourceBoM, resource_bom))
        bom_submodel_data = get_submodel_idshort(document, bom_submodel_uri)
        if bom_submodel_data:
            bom_entries = _add_bom_mapping(graph, bom_submodel_uri, bom_submodel_data)
            for entry in bom_entries:
                graph.add((resource_bom, CSSX.hasBoMItem, entry))

    nameplate_submodel_uri = find_submodel_by_type(
        present_submodels, AASV.DigitalNameplateSubmodel, graph)
    if nameplate_submodel_uri is not None:
        nameplate_submodel = get_submodel_idshort(
            document, nameplate_submodel_uri)
        if nameplate_submodel:
            add_nameplate_mapping(graph, resource, nameplate_submodel)

    if has_type(present_submodels, AASV.AIDSubmodel, graph):
        graph.add((software_interface, RDF.type, CSSX.SoftwareInterface))
        graph.add((resource, CSSX.hasResourceInterface, software_interface))

    if has_type(present_submodels, AASV.OperationalDataSubmodel, graph):
        operational_data = URIRef(f"{shell_id}#operational-data-1")
        graph.add((operational_data, RDF.type, CSSX.OperationalData))
        graph.add((resource, CSSX.hasOperationalData, operational_data))
        if software_interface is not None:
            graph.add((operational_data, CSSX.dataReferencesInterface, software_interface))

    if has_type(present_submodels, AASV.ParametersSubmodel, graph):
        parameter = URIRef(f"{shell_id}#resource-parameter-1")
        graph.add((parameter, RDF.type, CSSX.ResourceParameter))
        graph.add((resource, CSSX.hasResourceParameter, parameter))

    capabilities_submodel_uri = find_submodel_by_type(
        present_submodels, AASV.CapabilitiesSubmodel, graph)
    capability_by_idshort: dict[str, URIRef] = {}
    if capabilities_submodel_uri is not None:
        capabilities_submodel = get_submodel_idshort(
            document, capabilities_submodel_uri)
        if capabilities_submodel:
            capability_by_idshort = extract_capabilities(
                graph, resource, capabilities_submodel, test_flags)

    skills_submodel_uri = find_submodel_by_type(
        present_submodels, AASV.SkillsSubmodel, graph)
    skill_by_idshort: dict[str, URIRef] = {}
    if skills_submodel_uri is not None:
        skills_submodel = get_submodel_idshort(document, skills_submodel_uri)
        if skills_submodel:
            skill_by_idshort = extract_skills(
                graph, resource, skills_submodel, software_interface, test_flags)

    _link_capabilities_to_skills(
        graph,
        capability_by_idshort,
        skill_by_idshort,
        bool(test_flags.get("omitCapabilitySkillRealization", False)),
    )

    output_ttl.parent.mkdir(parents=True, exist_ok=True)
    graph.serialize(destination=str(output_ttl), format="turtle")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert a mock ResourceAAS JSON into an RDF graph for SHACL validation.")
    parser.add_argument("--input", required=True,
                        help="Path to ResourceAAS JSON input.")
    parser.add_argument("--output", required=True,
                        help="Path to output Turtle file.")
    arguments = parser.parse_args()

    convert(Path(arguments.input), Path(arguments.output))


if __name__ == "__main__":
    main()
