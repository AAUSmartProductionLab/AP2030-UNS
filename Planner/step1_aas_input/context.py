from __future__ import annotations

import logging
import traceback
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import requests

from .models import AIPlanningSource, _ParsedSource

logger = logging.getLogger(__name__)


@dataclass
class PlanningContext:
    order_config: Dict[str, Any]
    requirements: Dict[str, Any]
    resolved_asset_ids: List[str]
    planning_sources: List[AIPlanningSource]
    planar_table_id: Optional[str]
    asset_types_by_aas_id: Dict[str, str]
    # Phase 4: pre-parsed sources from KG (domain from projected apex:Action +
    # init from live predicate views).  When non-empty, the service skips
    # parse_source() and uses these directly.
    pre_parsed_sources: List[_ParsedSource] = field(default_factory=list)


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
    asset_types_by_aas_id = collect_asset_types_by_aas_id(
        aas_client,
        [order_aas_id] + [aid for aid in resolved_asset_ids if aid != order_aas_id],
    )
    planning_sources = collect_ai_planning_sources(aas_client, order_aas_id, resolved_asset_ids)
    planar_table_id = find_planar_table_from_assets(aas_client, resolved_asset_ids)

    return PlanningContext(
        order_config=order_config,
        requirements=requirements,
        resolved_asset_ids=resolved_asset_ids,
        planning_sources=planning_sources,
        planar_table_id=planar_table_id,
        asset_types_by_aas_id=asset_types_by_aas_id,
    )


def collect_planning_context_from_kg(
    aas_client: Any,
    order_aas_id: str,
    asset_ids: List[str],
    query_endpoint: str,
    abox_graph: str,
    tbox_graph: str,
    timeout_seconds: float = 10.0,
    enable_capability_matching: bool = True,
) -> Optional[PlanningContext]:
    """Collect planning context using KG capability matching and domain projection.

    Phase 4 integration:
    - Capability matching: select candidate resources from KG (Phase 4A).
    - Domain from KG: build _ParsedSource from projected apex:Action individuals
      (Phase 4B — uses apex:RefKey data from bridge ReferenceElement storage).
    - Problem.Init from KG: live predicate state from strategy views (Phase 4C option B).
    - Problem.Objects still read from AAS (PDDL names are AAS-authored; not in KG).
    Falls back gracefully to AAS-only mode on any KG failure.
    """
    from .kg_domain import collect_domain_sources_from_kg
    from .kg_problem import collect_init_from_kg, merge_init

    order_config = fetch_order_config(aas_client, order_aas_id)
    if not order_config:
        return None

    requirements = order_config.get("Requirements", {})
    selected_asset_ids = list(dict.fromkeys(asset_ids))

    if enable_capability_matching:
        required_capabilities = _extract_required_capability_ids(order_config)
        if required_capabilities:
            matched_from_kg = _select_resource_aas_ids_by_capability(
                required_capabilities=required_capabilities,
                query_endpoint=query_endpoint,
                abox_graph=abox_graph,
                tbox_graph=tbox_graph,
                timeout_seconds=timeout_seconds,
            )
            if matched_from_kg:
                selected_asset_ids = list(dict.fromkeys(list(asset_ids) + sorted(matched_from_kg)))
                logger.info("KG capability matching selected %d resource candidate(s)", len(matched_from_kg))
            else:
                logger.info("KG capability matching returned no candidates; falling back to provided assets")

    resolved_asset_ids = resolve_asset_hierarchies(aas_client, selected_asset_ids + [order_aas_id])
    asset_types_by_aas_id = collect_asset_types_by_aas_id(
        aas_client,
        [order_aas_id] + [aid for aid in resolved_asset_ids if aid != order_aas_id],
    )
    planar_table_id = find_planar_table_from_assets(aas_client, resolved_asset_ids)

    # ── Phase 4B: domain from KG projected apex:Action individuals ─────────────
    kg_domain_sources = collect_domain_sources_from_kg(
        query_endpoint=query_endpoint,
        abox_graph=abox_graph,
        tbox_graph=tbox_graph,
        timeout_seconds=timeout_seconds,
    )

    if kg_domain_sources:
        # ── Phase 4C: Problem.Objects + live KG init ───────────────────────────
        # Build AAS IRI → PDDL name mapping.
        # Primary: apex:aasIdShort literal stored by the bridge on each AAS node.
        # Fallback: AAS REST parsing if the KG doesn't yet have idShort data
        #           (e.g. legacy graph from before this bridge change).
        aas_iri_to_pddl_name: Dict[str, str] = _build_aas_name_map_from_kg(
            query_endpoint=query_endpoint,
            abox_graph=abox_graph,
            timeout_seconds=timeout_seconds,
        )

        # Read Problem.Objects from AAS (gives us author-chosen PDDL names +
        # types + location objects that aren't direct AAS IRIs).
        aas_planning_sources = collect_ai_planning_sources(aas_client, order_aas_id, resolved_asset_ids)

        # If KG name map is incomplete, fill gaps from AAS Problem.Objects.
        for aas_source in aas_planning_sources:
            if aas_source.aas_id not in aas_iri_to_pddl_name:
                top_elems = aas_source.ai_planning_submodel.get("submodelElements", [])
                from .parsing import find_collection
                problem = find_collection(top_elems, "Problem")
                if problem:
                    from .parsing import find_list, display_name as _dn
                    objects_section = find_list(problem.get("value", []), "Objects")
                    if objects_section:
                        for obj in (objects_section.get("value", []) or []):
                            obj_name = _dn(obj)
                            if obj_name:
                                aas_iri_to_pddl_name[aas_source.aas_id] = obj_name
                                break

        # Merge Problem.Objects + static init terms into each KG-domain source.
        aas_sources_by_id = {s.aas_id: s for s in aas_planning_sources}
        for kg_src in kg_domain_sources:
            aas_src = aas_sources_by_id.get(kg_src.aas_id)
            if aas_src:
                from .parsing import parse_problem, find_collection as _fc
                top_elems = aas_src.ai_planning_submodel.get("submodelElements", [])
                problem_section = _fc(top_elems, "Problem")
                if problem_section:
                    parse_problem(problem_section, kg_src,
                                  source_asset_type=aas_src.asset_type or "",
                                  asset_type_by_aas_id=asset_types_by_aas_id)

        # Augment init with KG live state; KG values override AAS for covered predicates.
        if aas_iri_to_pddl_name:
            live_init = collect_init_from_kg(
                aas_iri_to_pddl_name=aas_iri_to_pddl_name,
                query_endpoint=query_endpoint,
                abox_graph=abox_graph,
                tbox_graph=tbox_graph,
                timeout_seconds=timeout_seconds,
            )
            if live_init:
                for kg_src in kg_domain_sources:
                    kg_src.init_terms = merge_init(kg_src.init_terms, live_init)
                logger.info("Augmented Problem.Init with %d KG live term(s)", len(live_init))

        logger.info("Using KG-domain path: %d source(s)", len(kg_domain_sources))
        return PlanningContext(
            order_config=order_config,
            requirements=requirements,
            resolved_asset_ids=resolved_asset_ids,
            planning_sources=[],
            planar_table_id=planar_table_id,
            asset_types_by_aas_id=asset_types_by_aas_id,
            pre_parsed_sources=kg_domain_sources,
        )

    # ── Fallback: full AAS path ────────────────────────────────────────────────
    logger.info("No KG domain data available; falling back to AAS domain path")
    planning_sources = collect_ai_planning_sources(aas_client, order_aas_id, resolved_asset_ids)
    return PlanningContext(
        order_config=order_config,
        requirements=requirements,
        resolved_asset_ids=resolved_asset_ids,
        planning_sources=planning_sources,
        planar_table_id=planar_table_id,
        asset_types_by_aas_id=asset_types_by_aas_id,
    )


def _build_aas_name_map_from_kg(
    query_endpoint: str,
    abox_graph: str,
    timeout_seconds: float,
) -> Dict[str, str]:
    """Query apex:aasIdShort literals to build {aas_iri: idShort} map.

    Requires bridge to store apex:aasIdShort on AAS nodes (added in Phase 4).
    Returns empty dict on failure (caller falls back to AAS REST parsing).
    """
    query = f"""
PREFIX apex: <https://w3id.org/2026/apex/>
SELECT ?aas ?idShort
FROM <{abox_graph}>
WHERE {{
  ?aas apex:aasIdShort ?idShort .
}}
""".strip()
    try:
        response = requests.post(
            query_endpoint,
            data={"query": query},
            headers={"Accept": "application/sparql-results+json"},
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        bindings = response.json().get("results", {}).get("bindings", [])
        result: Dict[str, str] = {}
        for row in bindings:
            aas_iri = (row.get("aas") or {}).get("value")
            id_short = (row.get("idShort") or {}).get("value")
            if aas_iri and id_short:
                result[aas_iri] = id_short
        if result:
            logger.info("KG idShort map: %d entry(ies)", len(result))
        return result
    except Exception as exc:
        logger.debug("apex:aasIdShort query failed (bridge may not store it yet): %s", exc)
        return {}


def _extract_required_capability_ids(order_config: Dict[str, Any]) -> List[str]:
    required: List[str] = []
    processes = (order_config.get("BillOfProcesses") or {}).get("Processes") or []
    for process in processes:
        if not isinstance(process, dict):
            continue
        for _step_name, step_payload in process.items():
            if not isinstance(step_payload, dict):
                continue
            semantic_id = str(step_payload.get("semantic_id") or "").strip()
            if semantic_id:
                required.append(semantic_id)
    return list(dict.fromkeys(required))


def _normalize_semantic_iri(value: str) -> str:
    return value.strip().rstrip("/")


def _semantic_tail(value: str) -> str:
    normalized = _normalize_semantic_iri(value)
    if "#" in normalized:
        return normalized.rsplit("#", 1)[-1]
    if "/" in normalized:
        return normalized.rsplit("/", 1)[-1]
    return normalized


def _semantic_id_matches(left: str, right: str) -> bool:
    left_norm = _normalize_semantic_iri(left).lower()
    right_norm = _normalize_semantic_iri(right).lower()
    if left_norm == right_norm:
        return True
    return _semantic_tail(left_norm) == _semantic_tail(right_norm)


def _select_resource_aas_ids_by_capability(
    required_capabilities: List[str],
    query_endpoint: str,
    abox_graph: str,
    tbox_graph: str,
    timeout_seconds: float,
) -> List[str]:
    try:
        inventory = _query_resource_capability_inventory(
            query_endpoint=query_endpoint,
            abox_graph=abox_graph,
            tbox_graph=tbox_graph,
            timeout_seconds=timeout_seconds,
        )
    except Exception as exc:
        logger.warning("KG capability inventory query failed: %s", exc)
        return []

    matched: List[str] = []
    for aas_id, offered_semantics in inventory.items():
        if any(
            _semantic_id_matches(required, offered)
            for required in required_capabilities
            for offered in offered_semantics
        ):
            matched.append(aas_id)
    return matched


def _query_resource_capability_inventory(
    query_endpoint: str,
    abox_graph: str,
    tbox_graph: str,
    timeout_seconds: float,
) -> Dict[str, List[str]]:
    # Filter to AAS nodes that have at least one AI-Planning action mirrored in the KG.
    # Paths use the BaSyx element hierarchy relative to the submodel root: Domain.Actions.<ActionKey>.*
    # Under the identity IRI strategy the AAS node IRI *is* the AAS id, and the SME IRI is
    # <submodel-id>/submodel-elements/<path> — so STR(?aas) is directly usable by the AAS
    # client and the submodel join uses a single literal "/submodel-elements/" separator.
    query = f"""
PREFIX apex:  <https://w3id.org/2026/apex/>
PREFIX arso:  <https://w3id.org/2025/arso#>
PREFIX arsox: <https://w3id.org/aau-ra/arso-ext#>
PREFIX css:   <http://www.w3id.org/hsu-aut/css#>

SELECT DISTINCT ?aas ?providedCapability ?providedSkill
FROM <{tbox_graph}>
FROM <{abox_graph}>
WHERE {{
  ?aas a arsox:ResourceAssetAdministrationShell .

  FILTER EXISTS {{
    ?aas arso:hasSubmodel ?submodel .
    ?sme a apex:MirroredSubmodelElement ;
      apex:smElementPath ?actionPath .
    FILTER(STRSTARTS(STR(?actionPath), "Domain.Actions."))
    FILTER(STRSTARTS(STR(?sme), CONCAT(STR(?submodel), "/submodel-elements/")))
  }}

  OPTIONAL {{ ?aas css:providesCapability ?providedCapability . }}
  OPTIONAL {{ ?aas css:providesSkill ?providedSkill . }}
}}
""".strip()

    response = requests.post(
        query_endpoint,
        data={"query": query},
        headers={"Accept": "application/sparql-results+json"},
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    payload = response.json()

    inventory: Dict[str, List[str]] = {}
    for row in payload.get("results", {}).get("bindings", []):
        # Under identity strategy the AAS node IRI equals the raw AAS id.
        aas_id = (row.get("aas") or {}).get("value")
        if not aas_id:
            continue

        offered = []
        capability = (row.get("providedCapability") or {}).get("value")
        skill = (row.get("providedSkill") or {}).get("value")
        if capability:
            offered.append(capability)
        if skill:
            offered.append(skill)

        bucket = inventory.setdefault(aas_id, [])
        for semantic in offered:
            if semantic not in bucket:
                bucket.append(semantic)

    return inventory


def collect_asset_types_by_aas_id(aas_client: Any, aas_ids: List[str]) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for aas_id in aas_ids:
        if not aas_id or aas_id in mapping:
            continue
        try:
            shell = aas_client.get_aas_by_id(aas_id)
            asset_type = str(getattr(getattr(shell, "asset_information", None), "asset_type", "") or "")
            if asset_type:
                mapping[aas_id] = asset_type
        except Exception:
            continue
    return mapping


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
                    asset_type=str(getattr(getattr(shell, "asset_information", None), "asset_type", "") or ""),
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
