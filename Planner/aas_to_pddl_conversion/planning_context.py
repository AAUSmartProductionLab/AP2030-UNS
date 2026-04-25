from __future__ import annotations

import logging
import traceback
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .models import AIPlanningSource

logger = logging.getLogger(__name__)


@dataclass
class PlanningContext:
    order_config: Dict[str, Any]
    requirements: Dict[str, Any]
    resolved_asset_ids: List[str]
    planning_sources: List[AIPlanningSource]
    planar_table_id: Optional[str]


def collect_planning_context(
    aas_client: Any,
    order_aas_id: str,
    asset_ids: List[str],
) -> Optional[PlanningContext]:
    order_config = fetch_order_config(aas_client, order_aas_id)
    if not order_config:
        return None

    requirements = order_config.get("Requirements", {})
    # Walk hierarchies of both the explicitly-supplied resource asset_ids
    # AND the order itself. Multi-instance Orders carry their Product
    # Instance AASs as SelfManagedEntity children in HierarchicalStructures;
    # including the order in the resolution queue lets the planner pick up
    # each Instance's AIPlanning submodel automatically.
    resolved_asset_ids = resolve_asset_hierarchies(aas_client, list(asset_ids) + [order_aas_id])
    planning_sources = collect_ai_planning_sources(aas_client, order_aas_id, resolved_asset_ids)
    planar_table_id = find_planar_table_from_assets(aas_client, resolved_asset_ids)

    return PlanningContext(
        order_config=order_config,
        requirements=requirements,
        resolved_asset_ids=resolved_asset_ids,
        planning_sources=planning_sources,
        planar_table_id=planar_table_id,
    )


def fetch_order_config(aas_client: Any, order_aas_id: str) -> Optional[Dict[str, Any]]:
    """Fetch order AAS and convert to config format using BaSyx SDK."""
    from basyx.aas import model

    try:
        shell = aas_client.get_aas_by_id(order_aas_id)
        if not shell:
            return None

        config = {
            "id": shell.id,
            "idShort": shell.id_short,
            "globalAssetId": shell.asset_information.global_asset_id if shell.asset_information else "",
            "BatchInformation": {},
            "BillOfProcesses": {"Processes": []},
            "Requirements": {},
        }

        submodels = aas_client.get_submodels_from_aas(order_aas_id)
        logger.info("Found %d submodels for order AAS", len(submodels))
        for sm in submodels:
            logger.info("  Submodel: %s", sm.id_short)

        bill_of_processes_id = None
        for sm in submodels:
            if sm.id_short and sm.id_short.lower() == "billofprocesses":
                bill_of_processes_id = sm.id
                break

        if bill_of_processes_id:
            logger.info("Found BillOfProcesses submodel, fetching raw JSON...")
            bill_of_processes_raw = aas_client.get_submodel_raw(bill_of_processes_id)
            if bill_of_processes_raw:
                config["BillOfProcesses"] = parse_bill_of_processes_raw(bill_of_processes_raw)
        else:
            logger.warning("BillOfProcesses submodel not found")

        requirements = find_submodel(
            submodels,
            semantic_patterns=["Requirements", "ProductionRequirements"],
            id_short_patterns=["Requirements"],
        )
        if requirements:
            config["Requirements"] = parse_requirements(requirements)

        batch_info = find_submodel(
            submodels,
            semantic_patterns=["BatchInformation"],
            id_short_patterns=["BatchInformation"],
        )
        if batch_info:
            config["BatchInformation"] = parse_batch_info(batch_info)

        return config

    except Exception as exc:
        logger.error("Error fetching order config: %s", exc)
        traceback.print_exc()
        return None


def collect_ai_planning_sources(
    aas_client: Any,
    order_aas_id: str,
    asset_ids: List[str],
) -> List[AIPlanningSource]:
    """Collect AIPlanning sources from order and resolved assets."""
    source_ids: List[str] = [order_aas_id] + [asset_id for asset_id in asset_ids if asset_id != order_aas_id]
    sources: List[AIPlanningSource] = []

    for aas_id in source_ids:
        try:
            shell = aas_client.get_aas_by_id(aas_id)
            if not shell:
                continue

            submodels = aas_client.get_submodels_from_aas(aas_id)
            ai_planning_submodel_id = None
            for submodel in submodels:
                if submodel.id_short and submodel.id_short.lower() == "aiplanning":
                    ai_planning_submodel_id = submodel.id
                    break

            if not ai_planning_submodel_id:
                logger.debug("No AIPlanning submodel for %s", aas_id)
                continue

            ai_planning_raw = aas_client.get_submodel_raw(ai_planning_submodel_id)
            if not ai_planning_raw:
                logger.warning("AIPlanning submodel found but no raw payload for %s", aas_id)
                continue

            sources.append(
                AIPlanningSource(
                    aas_id=aas_id,
                    aas_name=shell.id_short or aas_id,
                    ai_planning_submodel=ai_planning_raw,
                )
            )
        except Exception as exc:
            logger.warning("Could not collect AIPlanning source for %s: %s", aas_id, exc)

    logger.info("Collected %d AIPlanning source(s)", len(sources))
    return sources


def find_planar_table_from_assets(aas_client: Any, asset_ids: List[str]) -> Optional[str]:
    """Find the planar table (motion system) by inspecting resolved assets."""
    for aas_id in asset_ids:
        try:
            shell = aas_client.get_aas_by_id(aas_id)
            if not shell or not shell.asset_information:
                continue
            asset_type = str(shell.asset_information.asset_type or "").lower()
            if "planartable" in asset_type or "motionsystem" in asset_type:
                return aas_id
        except Exception:
            continue
    return None


def find_submodel(submodels: Any, semantic_patterns: List[str], id_short_patterns: List[str]) -> Any:
    """Find a submodel by semantic_id patterns or id_short patterns."""
    for sm in submodels:
        if sm.semantic_id:
            for key in sm.semantic_id.key:
                sem_value = key.value.lower()
                for pattern in semantic_patterns:
                    if pattern.lower() in sem_value:
                        return sm

    for sm in submodels:
        id_short = sm.id_short.lower() if sm.id_short else ""
        for pattern in id_short_patterns:
            if pattern.lower() == id_short:
                return sm

    return None


def parse_bill_of_processes_raw(submodel_json: Dict[str, Any]) -> Dict[str, Any]:
    """Parse BillOfProcesses submodel from raw JSON."""
    result = {"Processes": [], "semantic_id": ""}

    if "semanticId" in submodel_json:
        keys = submodel_json["semanticId"].get("keys", [])
        if keys:
            result["semantic_id"] = keys[0].get("value", "")

    logger.info("Parsing BillOfProcesses from raw JSON")

    submodel_elements = submodel_json.get("submodelElements", [])
    logger.info("Raw JSON has %d top-level elements", len(submodel_elements))

    step_counter = 1
    for element in submodel_elements:
        model_type = element.get("modelType", "")
        id_short = element.get("idShort", "")
        logger.info("  Element: %s, type: %s", id_short, model_type)

        if model_type == "SubmodelElementList":
            items = element.get("value", [])
            logger.info("    SubmodelElementList with %d items", len(items))
            for step_elem in items:
                if step_elem.get("modelType") == "SubmodelElementCollection":
                    step_info = parse_process_step_raw(step_elem, step_counter)
                    if step_info:
                        result["Processes"].append(step_info)
                        step_counter += 1
        elif model_type == "SubmodelElementCollection":
            if id_short.lower() == "processes":
                items = element.get("value", [])
                logger.info("    Found 'Processes' container with %d items", len(items))
                for step_elem in items:
                    if step_elem.get("modelType") == "SubmodelElementCollection":
                        step_info = parse_process_step_raw(step_elem, step_counter)
                        if step_info:
                            result["Processes"].append(step_info)
                            step_counter += 1
            else:
                step_info = parse_process_step_raw(element, step_counter)
                if step_info:
                    result["Processes"].append(step_info)
                    step_counter += 1

    logger.info("Parsed %d processes from raw JSON", len(result["Processes"]))
    return result


def parse_process_step_raw(element: Dict[str, Any], step_num: int) -> Optional[Dict[str, Any]]:
    """Parse a single process step from raw JSON dict."""
    name = element.get("idShort", "")

    display_name = element.get("displayName", [])
    if display_name:
        for lang_entry in display_name:
            if isinstance(lang_entry, dict):
                if lang_entry.get("language", "").startswith("en"):
                    name = lang_entry.get("text", name)
                    break
        if not name and display_name:
            first_entry = display_name[0]
            if isinstance(first_entry, dict):
                name = first_entry.get("text", "")

    step_config = {
        "step": step_num,
        "semantic_id": "",
        "process_semantic_id": "",
        "description": "",
        "estimatedDuration": 0.0,
        "parameters": {},
    }

    if "semanticId" in element:
        keys = element["semanticId"].get("keys", [])
        if keys:
            step_config["process_semantic_id"] = keys[0].get("value", "")

    for child in element.get("value", []):
        model_type = child.get("modelType", "")
        child_id = child.get("idShort", "").lower()

        if model_type == "Property":
            if child_id == "step":
                step_config["step"] = int(child.get("value", step_num))
            elif child_id == "description":
                step_config["description"] = child.get("value", "")
            elif child_id in ["estimatedduration", "duration"]:
                step_config["estimatedDuration"] = float(child.get("value", 0))
        elif model_type == "ReferenceElement":
            if child_id == "requiredcapability":
                ref_value = child.get("value", {})
                keys = ref_value.get("keys", [])
                if keys:
                    step_config["semantic_id"] = keys[0].get("value", "")
        elif model_type == "SubmodelElementCollection":
            if child_id == "parameters":
                step_config["parameters"] = parse_parameters_raw(child)

    if not step_config["semantic_id"] and step_config["process_semantic_id"]:
        step_config["semantic_id"] = step_config["process_semantic_id"]

    if not name and step_config["process_semantic_id"]:
        name = step_config["process_semantic_id"].split("/")[-1]

    return {name: step_config}


def parse_parameters_raw(collection: Dict[str, Any]) -> Dict[str, Any]:
    """Parse parameters collection from raw JSON."""
    params = {}
    for child in collection.get("value", []):
        if child.get("modelType") == "Property":
            id_short = child.get("idShort", "")
            value = child.get("value")
            if id_short:
                params[id_short] = value
    return params


def parse_requirements(submodel: Any) -> Dict[str, Any]:
    """Parse Requirements submodel into config format."""
    from basyx.aas import model

    result = {
        "Environmental": {},
        "InProcessControl": {},
        "QualityControl": {},
    }

    for element in submodel.submodel_element:
        if isinstance(element, model.SubmodelElementCollection):
            category = element.id_short
            if category in result:
                result[category] = parse_requirement_collection(element)

    return result


def parse_requirement_collection(collection: Any) -> Dict[str, Any]:
    """Parse a requirement category collection."""
    from basyx.aas import model

    result = {}
    for elem in collection.value:
        if isinstance(elem, model.SubmodelElementCollection):
            req_config = {}
            for prop in elem.value:
                if isinstance(prop, model.Property):
                    prop_name = prop.id_short.lower()
                    if prop_name in ["rate", "value"]:
                        req_config[prop_name] = float(prop.value) if prop.value else 0
                    elif prop_name == "unit":
                        req_config["unit"] = str(prop.value) if prop.value else ""
                    elif prop_name == "semantic_id":
                        req_config["semantic_id"] = str(prop.value) if prop.value else ""
                    elif prop_name == "appliesto":
                        req_config["appliesTo"] = str(prop.value) if prop.value else ""

            result[elem.id_short] = req_config

    return result


def parse_batch_info(submodel: Any) -> Dict[str, Any]:
    """Parse BatchInformation submodel."""
    from basyx.aas import model

    result = {}
    for element in submodel.submodel_element:
        if isinstance(element, model.Property):
            value = element.value
            if element.id_short in ["Quantity"]:
                result[element.id_short] = int(value) if value else 0
            else:
                result[element.id_short] = str(value) if value else ""

    return result


def resolve_asset_hierarchies(aas_client: Any, asset_ids: List[str]) -> List[str]:
    """Resolve hierarchical structures to find all available assets recursively."""
    all_assets = []
    seen = set()

    queue = list(asset_ids)

    while queue:
        aas_id = queue.pop(0)

        if aas_id in seen:
            continue
        seen.add(aas_id)
        all_assets.append(aas_id)

        try:
            hierarchy_submodel = aas_client.find_submodel_by_semantic_id(
                aas_id,
                "HierarchicalStructures",
            )

            if hierarchy_submodel:
                child_ids = resolve_hierarchy_submodel(aas_client, hierarchy_submodel)
                for child_id in child_ids:
                    if child_id not in seen:
                        queue.append(child_id)
            else:
                logger.debug("No HierarchicalStructures found for %s", aas_id)

        except Exception as exc:
            logger.warning("Could not resolve hierarchy for %s: %s", aas_id, exc)
            traceback.print_exc()

    return all_assets


def resolve_hierarchy_submodel(aas_client: Any, submodel: Any) -> List[str]:
    """Recursively resolve hierarchical structure to extract all AAS IDs."""
    from basyx.aas import model

    aas_ids = []

    try:
        archetype = None
        for element in submodel.submodel_element:
            if element.id_short in ["ArcheType", "Archetype"] and isinstance(element, model.Property):
                archetype = str(element.value)
                break

        if archetype != "OneDown":
            return aas_ids

        for element in submodel.submodel_element:
            if element.id_short == "EntryNode" and isinstance(element, model.Entity):
                for statement in element.statement:
                    if isinstance(statement, model.Entity):
                        child_aas_id = None
                        child_hierarchy_submodel_id = None

                        for sub_statement in statement.statement:
                            if isinstance(sub_statement, model.ReferenceElement) and sub_statement.id_short == "SameAs":
                                if sub_statement.value:
                                    for key in sub_statement.value.key:
                                        if key.type == model.KeyTypes.SUBMODEL:
                                            child_hierarchy_submodel_id = key.value
                                            child_aas_id = extract_aas_id_from_submodel_id(
                                                aas_client,
                                                child_hierarchy_submodel_id,
                                            )
                                            break

                        if not child_aas_id and statement.global_asset_id:
                            child_aas_id = aas_client.lookup_aas_by_asset_id(statement.global_asset_id)

                        if child_aas_id:
                            aas_ids.append(child_aas_id)

                        if child_hierarchy_submodel_id:
                            try:
                                referenced_submodel = aas_client.get_submodel_by_id(child_hierarchy_submodel_id)
                                if referenced_submodel:
                                    child_aas_ids = resolve_hierarchy_submodel(aas_client, referenced_submodel)
                                    aas_ids.extend(child_aas_ids)
                            except Exception as exc:
                                logger.debug("Could not follow SameAs reference: %s", exc)
                break

    except Exception as exc:
        logger.warning("Error in resolve_hierarchy_submodel: %s", exc)
        traceback.print_exc()

    return aas_ids


def extract_aas_id_from_submodel_id(aas_client: Any, submodel_id: str) -> Optional[str]:
    """Extract AAS ID from a submodel ID pattern."""
    try:
        parts = submodel_id.split("/")
        if "instances" in parts:
            idx = parts.index("instances")
            if idx + 1 < len(parts):
                aas_id_short = parts[idx + 1]
                possible_aas_ids = [
                    f"https://smartproductionlab.aau.dk/aas/{aas_id_short}",
                    f"https://smartproductionlab.aau.dk/aas/{aas_id_short.replace('AAS', '')}",
                ]
                for possible_id in possible_aas_ids:
                    try:
                        shell = aas_client.get_aas_by_id(possible_id)
                        if shell:
                            return possible_id
                    except Exception:
                        continue
    except Exception as exc:
        logger.debug("Could not extract AAS ID from submodel ID: %s", exc)

    return None
