import argparse
import json
from pathlib import Path

import yaml


def first_text(value):
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict) and item.get("text"):
                return str(item["text"])
    return None


def find_child(collection: dict, id_short: str):
    for item in collection.get("value", []):
        if isinstance(item, dict) and item.get("idShort") == id_short:
            return item
    return None


def child_property_value(collection: dict, id_short: str):
    item = find_child(collection, id_short)
    if not item:
        return None
    if item.get("modelType") == "Property":
        return item.get("value")
    if item.get("modelType") == "MultiLanguageProperty":
        return first_text(item.get("value"))
    return None


def extract_semantic_id_from_collection(collection: dict):
    value = child_property_value(collection, "SemanticId")
    if value:
        return str(value)
    return None


def extract_interface_reference_name(collection: dict):
    ref = find_child(collection, "InterfaceReference")
    if not ref or ref.get("modelType") != "ReferenceElement":
        return None
    keys = ref.get("value", {}).get("keys", [])
    if not isinstance(keys, list) or not keys:
        return None
    tail = keys[-1]
    if isinstance(tail, dict):
        return tail.get("value")
    return None


def extract_operation_name(skill_collection: dict):
    for child in skill_collection.get("value", []):
        if isinstance(child, dict) and child.get("modelType") == "Operation":
            return child.get("idShort")
    return None


def submodels_by_idshort(document: dict):
    return {
        sm.get("idShort"): sm
        for sm in document.get("submodels", [])
        if isinstance(sm, dict) and sm.get("modelType") == "Submodel" and sm.get("idShort")
    }


def build_yaml_config(document: dict):
    shells = document.get("assetAdministrationShells", [])
    if not shells:
        raise ValueError("No assetAdministrationShells found")

    shell = shells[0]
    system_id = shell.get("idShort") or "ResourceAAS"
    config = {
        "idShort": shell.get("idShort"),
        "id": shell.get("id"),
        "globalAssetId": (shell.get("assetInformation") or {}).get("globalAssetId"),
    }

    sm = submodels_by_idshort(document)

    nameplate = sm.get("DigitalNameplate")
    if nameplate:
        digital_nameplate = {}
        for element in nameplate.get("submodelElements", []):
            if not isinstance(element, dict):
                continue
            id_short = element.get("idShort")
            if not id_short:
                continue
            if element.get("modelType") == "Property":
                value = element.get("value")
            elif element.get("modelType") == "MultiLanguageProperty":
                value = first_text(element.get("value"))
            else:
                continue
            if value not in (None, ""):
                digital_nameplate[id_short] = value
        if digital_nameplate:
            config["DigitalNameplate"] = digital_nameplate

    aid = sm.get("AID")
    if aid and aid.get("submodelElements"):
        first_interface = aid.get("submodelElements", [])[0]
        aid_config = {"InterfaceMQTT": {
            "InteractionMetadata": {"actions": {}, "properties": {}}}}

        title = child_property_value(first_interface, "title")
        if title:
            aid_config["InterfaceMQTT"]["Title"] = title

        endpoint = find_child(first_interface, "EndpointMetadata")
        if endpoint:
            endpoint_metadata = {}
            base = child_property_value(endpoint, "base")
            content_type = child_property_value(endpoint, "contentType")
            if base:
                endpoint_metadata["base"] = base
            if content_type:
                endpoint_metadata["contentType"] = content_type
            if endpoint_metadata:
                aid_config["InterfaceMQTT"]["EndpointMetadata"] = endpoint_metadata

        interaction = find_child(first_interface, "InteractionMetadata")
        if interaction:
            properties_container = find_child(interaction, "properties")
            if properties_container:
                for prop in properties_container.get("value", []):
                    if not isinstance(prop, dict):
                        continue
                    prop_name = prop.get("idShort")
                    if not prop_name:
                        continue
                    out = {
                        "key": prop_name,
                    }
                    prop_title = child_property_value(prop, "title")
                    if prop_title:
                        out["title"] = prop_title
                    forms = find_child(prop, "forms")
                    if forms:
                        forms_obj = {}
                        for form_item in forms.get("value", []):
                            if not isinstance(form_item, dict):
                                continue
                            fid = form_item.get("idShort")
                            if not fid:
                                continue
                            if form_item.get("modelType") == "Property":
                                forms_obj[fid] = form_item.get("value")
                        if forms_obj:
                            out["forms"] = forms_obj
                    aid_config["InterfaceMQTT"]["InteractionMetadata"]["properties"][prop_name] = out

        config["AID"] = aid_config

    operational_data = sm.get("OperationalData")
    if operational_data:
        operational_data_cfg = {}
        for element in operational_data.get("submodelElements", []):
            if not isinstance(element, dict) or element.get("modelType") != "SubmodelElementCollection":
                continue
            var_name = element.get("idShort")
            if not var_name:
                continue
            var_cfg = {}
            semantic_id = extract_semantic_id_from_collection(element)
            if semantic_id:
                var_cfg["semanticId"] = semantic_id
            interface_ref = extract_interface_reference_name(element)
            if interface_ref:
                var_cfg["InterfaceReference"] = interface_ref
            measured_value = child_property_value(element, "MeasuredValue")
            if measured_value is not None:
                var_cfg["MeasuredValue"] = measured_value
            if var_cfg:
                operational_data_cfg[var_name] = var_cfg
        if operational_data_cfg:
            config["OperationalData"] = operational_data_cfg

    parameters = sm.get("Parameters")
    if parameters:
        params_cfg = {}
        for element in parameters.get("submodelElements", []):
            if not isinstance(element, dict) or element.get("modelType") != "SubmodelElementCollection":
                continue
            param_name = element.get("idShort")
            if not param_name:
                continue
            param_cfg = {}
            semantic_id = extract_semantic_id_from_collection(element)
            if semantic_id:
                param_cfg["semanticId"] = semantic_id
            param_value = child_property_value(element, "ParameterValue")
            if param_value is not None:
                param_cfg["ParameterValue"] = param_value
            unit = child_property_value(element, "Unit")
            if unit is not None:
                param_cfg["Unit"] = unit
            if param_cfg:
                params_cfg[param_name] = param_cfg
        config["Parameters"] = params_cfg if params_cfg else {}

    hierarchy = sm.get("HierarchicalStructures")
    if hierarchy:
        hs_cfg = {}
        archetype = child_property_value(hierarchy, "ArcheType")
        if archetype:
            hs_cfg["Archetype"] = archetype
        first_entity = None
        for element in hierarchy.get("submodelElements", []):
            if isinstance(element, dict) and element.get("modelType") == "Entity":
                first_entity = element
                break
        if first_entity and first_entity.get("idShort"):
            hs_cfg["Name"] = first_entity.get("idShort")
        if hs_cfg:
            config["HierarchicalStructures"] = hs_cfg

    capabilities = sm.get("Capabilities")
    if capabilities:
        cap_cfg = {}
        for element in capabilities.get("submodelElements", []):
            if not isinstance(element, dict) or element.get("modelType") != "SubmodelElementCollection":
                continue
            cap_name = element.get("idShort")
            if not cap_name:
                continue
            semantic_id = extract_semantic_id_from_collection(element)
            entry = {}
            if semantic_id:
                entry["semantic_id"] = semantic_id
            cap_cfg[cap_name] = entry
        if cap_cfg:
            config["Capabilities"] = cap_cfg

    skills = sm.get("Skills")
    if skills:
        skills_cfg = {}
        for element in skills.get("submodelElements", []):
            if not isinstance(element, dict) or element.get("modelType") != "SubmodelElementCollection":
                continue
            skill_name = element.get("idShort")
            if not skill_name:
                continue
            entry = {}
            semantic_id = extract_semantic_id_from_collection(element)
            if semantic_id:
                entry["semantic_id"] = semantic_id
            display_name = child_property_value(element, "DisplayName")
            if display_name:
                entry["description"] = str(display_name)
            interface_name = extract_operation_name(element)
            if interface_name:
                entry["interface"] = interface_name
            skills_cfg[skill_name] = entry
        if skills_cfg:
            config["Skills"] = skills_cfg

    return {system_id: config}


def main():
    parser = argparse.ArgumentParser(
        description="Convert ResourceAAS JSON document to generator YAML format.")
    parser.add_argument("--input", required=True,
                        help="Path to input ResourceAAS JSON file")
    parser.add_argument("--output", required=True,
                        help="Path to output YAML file")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    with input_path.open("r", encoding="utf-8") as handle:
        document = json.load(handle)

    converted = build_yaml_config(document)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(converted, handle, sort_keys=False, allow_unicode=True)

    print(f"Wrote YAML to {output_path}")


if __name__ == "__main__":
    main()
