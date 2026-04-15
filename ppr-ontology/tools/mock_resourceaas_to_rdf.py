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
        "ManufacturerProductRoot": (CSSX.manufacturerProductRoot, None),
        "ManufacturerProductType": (CSSX.manufacturerProductType, None),
        "ManufacturerArticleNumber": (CSSX.productArticleNumberOfManufacturer, None),
        "SerialNumber": (CSSX.serialNumber, None),
        "BatchNumber": (CSSX.batchNumber, None),
        "YearOfConstruction": (CSSX.yearOfConstruction, None),
        "DateOfManufacture": (CSSX.dateOfManufacture, None),
        "HardwareVersion": (CSSX.hardwareVersion, None),
        "FirmwareVersion": (CSSX.firmwareVersion, None),
        "SoftwareVersion": (CSSX.softwareVersion, None),
        "CountryOfOrigin": (CSSX.countryOfOrigin, None),
        "CompanyLogo": (CSSX.companyLogoUri, XSD.anyURI),
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

        predicate, forced_datatype = mapped
        if model_type == "Property":
            value = element.get("value")
            if value not in (None, ""):
                value_str = str(value)
                if forced_datatype == XSD.anyURI:
                    graph.add((resource, predicate, Literal(value_str, datatype=XSD.anyURI)))
                elif predicate == CSSX.yearOfConstruction:
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
                if language and predicate in {CSSX.manufacturerProductDesignation, CSSX.manufacturerProductFamily,
                                              CSSX.manufacturerProductRoot, CSSX.manufacturerProductType}:
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

        _extract_skill_sub_elements(graph, skill_uri, skill_idshort, element)

    return skill_by_idshort


def _extract_skill_sub_elements(graph: Graph, skill_uri: URIRef, skill_idshort: str, element: dict) -> None:
    """Extract PPR-specific skill sub-structures (Condition, Effects, Predicate) and standard CSS SkillParameters."""
    _PPR_CONDITION_SEMANTIC = "https://smartproductionlab.aau.dk/PPR/SkillDescription/Condition"
    _PPR_EFFECTS_SEMANTIC = "https://smartproductionlab.aau.dk/PPR/SkillDescription/Effects"
    _PPR_PREDICATE_SEMANTIC = "https://smartproductionlab.aau.dk/PPR/SkillDescription/Predicate"

    display_name = None
    for child in element.get("value", []):
        if not isinstance(child, dict):
            continue
        child_idshort = str(child.get("idShort", "")).strip()
        child_model_type = child.get("modelType", "")
        child_semantic = first_semantic_id(child)

        if child_idshort == "DisplayName" and child_model_type == "MultiLanguageProperty":
            display_name = first_multilang_text(child)

        elif child_model_type == "SubmodelElementCollection":
            child_idshort_lower = child_idshort.lower()

            # Standard CSS: InputParameter / OutputParameter
            if "inputparameter" in child_idshort_lower or "outputparameter" in child_idshort_lower:
                param_type = CSS.InputParameter if "input" in child_idshort_lower else CSS.OutputParameter
                param_uri = URIRef(f"{skill_uri}#param-{normalize_local_name(child_idshort)}")
                graph.add((param_uri, RDF.type, CSS.SkillParameter))
                graph.add((param_uri, RDF.type, param_type))
                graph.add((skill_uri, CSS.hasParameter, param_uri))
                graph.add((param_uri, AASV.sourceIdShort, Literal(child_idshort)))
                continue

            # Standard CSS: Trigger
            if "trigger" in child_idshort_lower:
                trigger_uri = URIRef(f"{skill_uri}#trigger-{normalize_local_name(child_idshort)}")
                graph.add((trigger_uri, RDF.type, CSS.SkillTrigger))
                graph.add((skill_uri, CSS.hasTrigger, trigger_uri))
                graph.add((trigger_uri, AASV.sourceIdShort, Literal(child_idshort)))
                continue

            # PPR-specific: Condition
            is_condition = (child_idshort == "Condition" or
                            (child_semantic and "Condition" in child_semantic))
            if is_condition:
                cond_uri = URIRef(f"{skill_uri}#condition-{normalize_local_name(child_idshort)}")
                graph.add((cond_uri, RDF.type, CSSX.SkillCondition))
                graph.add((skill_uri, CSSX.hasSkillCondition, cond_uri))
                graph.add((cond_uri, AASV.sourceIdShort, Literal(child_idshort)))
                if child_semantic:
                    graph.add((cond_uri, AASV.sourceSemanticId, Literal(child_semantic)))
                continue

            # PPR-specific: Effects
            is_effects = (child_idshort == "Effects" or
                          (child_semantic and "Effects" in child_semantic))
            if is_effects:
                effect_uri = URIRef(f"{skill_uri}#effects-{normalize_local_name(child_idshort)}")
                graph.add((effect_uri, RDF.type, CSSX.SkillEffect))
                graph.add((skill_uri, CSSX.hasSkillEffect, effect_uri))
                graph.add((effect_uri, AASV.sourceIdShort, Literal(child_idshort)))
                if child_semantic:
                    graph.add((effect_uri, AASV.sourceSemanticId, Literal(child_semantic)))
                continue

            # PPR-specific: Predicate (e.g. Predicate_IsExecutable)
            is_predicate = ("predicate" in child_idshort_lower or
                            (child_semantic and "Predicate" in child_semantic))
            if is_predicate:
                pred_uri = URIRef(f"{skill_uri}#predicate-{normalize_local_name(child_idshort)}")
                graph.add((pred_uri, RDF.type, CSSX.SkillPredicate))
                graph.add((skill_uri, CSSX.hasSkillPredicate, pred_uri))
                graph.add((pred_uri, AASV.sourceIdShort, Literal(child_idshort)))
                if child_semantic:
                    graph.add((pred_uri, AASV.sourceSemanticId, Literal(child_semantic)))
                body = element_property_value(child, "BodyExpression")
                if body:
                    graph.add((pred_uri, RDFS.comment, Literal(body)))
                continue

    if display_name:
        graph.add((skill_uri, RDFS.label, Literal(display_name)))


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


def add_aid_mapping(graph: Graph, resource: URIRef, aid_submodel: dict, software_interface: URIRef) -> None:
    """Extract AID interface metadata into RDF (endpoint base URI, content type, interaction names)."""
    for interface_element in aid_submodel.get("submodelElements", []):
        if not isinstance(interface_element, dict):
            continue
        if interface_element.get("modelType") != "SubmodelElementCollection":
            continue

        interface_idshort = str(interface_element.get("idShort", "")).strip()
        interface_safe = normalize_local_name(interface_idshort) if interface_idshort else "interface"
        interface_uri = URIRef(f"{software_interface}#{interface_safe}")
        graph.add((interface_uri, RDF.type, CSSX.SoftwareInterface))
        graph.add((resource, CSSX.hasResourceInterface, interface_uri))

        for child in interface_element.get("value", []):
            if not isinstance(child, dict):
                continue
            child_idshort = child.get("idShort", "")

            if child.get("modelType") == "Property" and child_idshort == "title":
                title_val = child.get("value")
                if title_val:
                    graph.add((interface_uri, CSSX.interfaceTitle, Literal(str(title_val))))

            elif child_idshort == "EndpointMetadata" and child.get("modelType") == "SubmodelElementCollection":
                for meta in child.get("value", []):
                    if not isinstance(meta, dict) or meta.get("modelType") != "Property":
                        continue
                    meta_idshort = meta.get("idShort", "")
                    meta_val = meta.get("value")
                    if not meta_val:
                        continue
                    if meta_idshort == "base":
                        graph.add((interface_uri, CSSX.endpointBaseUri, Literal(str(meta_val), datatype=XSD.anyURI)))
                    elif meta_idshort == "contentType":
                        graph.add((interface_uri, CSSX.interfaceContentType, Literal(str(meta_val))))

            elif child_idshort == "InteractionMetadata" and child.get("modelType") == "SubmodelElementCollection":
                for category_elem in child.get("value", []):
                    if not isinstance(category_elem, dict):
                        continue
                    if category_elem.get("modelType") != "SubmodelElementCollection":
                        continue
                    category_name = str(category_elem.get("idShort", "")).strip()
                    for interaction in category_elem.get("value", []):
                        if not isinstance(interaction, dict):
                            continue
                        if interaction.get("modelType") != "SubmodelElementCollection":
                            continue
                        interaction_name = str(interaction.get("idShort", "")).strip()
                        if not interaction_name:
                            continue
                        interaction_safe = normalize_local_name(interaction_name)
                        interaction_uri = URIRef(f"{interface_uri}#interaction-{interaction_safe}")
                        graph.add((interaction_uri, RDF.type, CSSX.InteractionMetadata))
                        graph.add((interface_uri, CSSX.hasInteractionMetadata, interaction_uri))
                        graph.add((interaction_uri, CSSX.interactionName, Literal(interaction_name)))
                        graph.add((interaction_uri, CSSX.interactionCategory, Literal(category_name)))


def add_operational_data_mapping(graph: Graph, resource: URIRef, operational_data_uri: URIRef,
                                 opdata_submodel: dict, software_interface: URIRef | None) -> None:
    """Extract OperationalData submodel elements as DataConcept metadata nodes.

    DataConcept nodes carry source idShort and semanticId so SHACL rules can verify
    which data points the AAS declares.  We intentionally avoid using properties with
    domain ``MeasurementData`` (e.g. ``measurementTimestamp``, ``hasMeasuredValue``)
    because RDFS domain inference would retype the DataConcept as MeasurementData and
    trigger cardinality constraints that don't apply to a pure metadata projection.
    """
    for element in opdata_submodel.get("submodelElements", []):
        if not isinstance(element, dict):
            continue
        if element.get("modelType") != "SubmodelElementCollection":
            continue

        elem_idshort = str(element.get("idShort", "")).strip()
        if not elem_idshort:
            continue

        safe = normalize_local_name(elem_idshort)
        concept_uri = URIRef(f"{operational_data_uri}#{safe}")
        graph.add((concept_uri, RDF.type, CSSX.DataConcept))
        graph.add((operational_data_uri, CSSX.hasDataConcept, concept_uri))
        graph.add((concept_uri, AASV.sourceIdShort, Literal(elem_idshort)))

        semantic = first_semantic_id(element)
        if semantic:
            graph.add((concept_uri, AASV.sourceSemanticId, Literal(semantic)))


def add_parameters_mapping(graph: Graph, resource: URIRef, parameter_uri: URIRef, parameters_submodel: dict) -> None:
    """Extract Parameters submodel elements into ResourceParameter RDF nodes."""
    for element in parameters_submodel.get("submodelElements", []):
        if not isinstance(element, dict):
            continue
        if element.get("modelType") != "SubmodelElementCollection":
            continue

        param_idshort = str(element.get("idShort", "")).strip()
        if not param_idshort:
            continue

        safe = normalize_local_name(param_idshort)
        param_node = URIRef(f"{parameter_uri}#{safe}")
        graph.add((param_node, RDF.type, CSSX.ResourceParameter))
        graph.add((resource, CSSX.hasResourceParameter, param_node))
        graph.add((param_node, AASV.sourceIdShort, Literal(param_idshort)))

        semantic = first_semantic_id(element)
        if semantic:
            graph.add((param_node, AASV.sourceSemanticId, Literal(semantic)))

        for child in element.get("value", []):
            if not isinstance(child, dict):
                continue
            child_idshort = child.get("idShort", "")
            child_model_type = child.get("modelType", "")

            if child_idshort == "DisplayName" and child_model_type == "MultiLanguageProperty":
                entry = first_multilang_entry(child)
                if entry:
                    text, language = entry
                    if language:
                        graph.add((param_node, CSSX.parameterName, Literal(text, lang=language)))
                    else:
                        graph.add((param_node, CSSX.parameterName, Literal(text)))

            elif child_model_type == "Property":
                prop_val = child.get("value")
                if prop_val in (None, ""):
                    continue
                if child_idshort == "ParameterValue":
                    graph.add((param_node, CSSX.parameterValue, Literal(str(prop_val))))
                elif child_idshort == "Unit":
                    graph.add((param_node, CSSX.parameterUnit, Literal(str(prop_val))))
                elif child_idshort == "IsReadOnly":
                    bool_val = str(prop_val).lower() in ("true", "1", "yes")
                    graph.add((param_node, CSSX.isReadOnly, Literal(bool_val, datatype=XSD.boolean)))
                elif child_idshort == "Scope":
                    graph.add((param_node, CSSX.scopeValue, Literal(str(prop_val))))
                elif child_idshort == "ParameterValueType":
                    graph.add((param_node, CSSX.parameterValueType, Literal(str(prop_val))))


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

    aid_submodel_uri = find_submodel_by_type(present_submodels, AASV.AIDSubmodel, graph)
    if aid_submodel_uri is not None:
        graph.add((software_interface, RDF.type, CSSX.SoftwareInterface))
        graph.add((resource, CSSX.hasResourceInterface, software_interface))
        aid_submodel_data = get_submodel_idshort(document, aid_submodel_uri)
        if aid_submodel_data:
            add_aid_mapping(graph, resource, aid_submodel_data, software_interface)

    opdata_submodel_uri = find_submodel_by_type(present_submodels, AASV.OperationalDataSubmodel, graph)
    if opdata_submodel_uri is not None:
        operational_data = URIRef(f"{shell_id}#operational-data-1")
        graph.add((operational_data, RDF.type, CSSX.OperationalData))
        graph.add((resource, CSSX.hasOperationalData, operational_data))
        if software_interface is not None:
            graph.add((operational_data, CSSX.dataReferencesInterface, software_interface))
        opdata_submodel_data = get_submodel_idshort(document, opdata_submodel_uri)
        if opdata_submodel_data:
            add_operational_data_mapping(graph, resource, operational_data, opdata_submodel_data, software_interface)

    params_submodel_uri = find_submodel_by_type(present_submodels, AASV.ParametersSubmodel, graph)
    if params_submodel_uri is not None:
        parameter = URIRef(f"{shell_id}#resource-parameter-1")
        graph.add((parameter, RDF.type, CSSX.ResourceParameter))
        graph.add((resource, CSSX.hasResourceParameter, parameter))
        params_submodel_data = get_submodel_idshort(document, params_submodel_uri)
        if params_submodel_data:
            add_parameters_mapping(graph, resource, parameter, params_submodel_data)

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
