#!/usr/bin/env python3
"""Standalone production planner using AAS for configuration"""

import datetime
from xml.etree import ElementTree as ET
from typing import List, Dict, Optional
from basyx.aas import model
from basyx.aas.model import provider
from aas_client import AASClient
import os

AAS_SERVER_URL = os.getenv("AAS_SERVER_URL", "http://aas-env:8081")
AAS_REGISTRY_URL = os.getenv("AAS_REGISTRY_URL", "http://aas-registry:8080")

# Initialize AAS client and object store for caching
aas_client = AASClient(AAS_SERVER_URL, AAS_REGISTRY_URL)
object_store = provider.DictObjectStore()


def fetch_product_info(product_aas_id: str) -> Optional[Dict[str, any]]:
    """Fetch product information from product AAS

    Args:
        product_aas_id: The product AAS identifier

    Returns:
        Dictionary with product information or None
    """
    try:
        # Fetch the AAS shell using aas_client
        shell = aas_client.get_aas_by_id(product_aas_id)

        if not shell:
            print(f"Warning: Could not fetch product AAS {product_aas_id}")
            return None

        # Cache in object store
        if shell.id not in [obj.id for obj in object_store]:
            object_store.add(shell)

        product_info = {
            'aas_id': product_aas_id,
            'id_short': shell.id_short,
            'global_asset_id': shell.asset_information.global_asset_id if shell.asset_information else '',
            'requirements': {},
            'processes': []
        }

        # Fetch Requirements submodel
        try:
            requirement_submodel = aas_client.find_submodel_by_semantic_id(
                product_aas_id, 'Requirements'
            )
            if requirement_submodel:
                # Cache submodel
                if requirement_submodel.id not in [obj.id for obj in object_store]:
                    object_store.add(requirement_submodel)

                # Extract quality control requirements - use proper type checking
                for element in requirement_submodel.submodel_element:
                    if element.id_short == 'QualityControl' and isinstance(element, model.SubmodelElementCollection):
                        for prop in element.value:
                            if isinstance(prop, model.Property) and prop.id_short == 'QCSamples':
                                product_info['requirements']['qc_inspection_rate'] = str(
                                    prop.value)
                    if element.id_short == 'InProcessControls' and isinstance(element, model.SubmodelElementCollection):
                        for prop in element.value:
                            if isinstance(prop, model.Property) and prop.id_short == 'IPCInspection':
                                product_info['requirements']['ipc_inspection_amount'] = str(
                                    prop.value)
                            if isinstance(prop, model.Property) and prop.id_short == 'IPCInspectionUnit':
                                product_info['requirements']['ipc_inspection_unit'] = str(
                                    prop.value)
        except Exception as e:
            pass

        # Fetch Bill of Processes
        try:
            bill_of_processes_submodel = aas_client.find_submodel_by_semantic_id(
                product_aas_id, 'BillOfProcesses'
            )
            if bill_of_processes_submodel:
                # Cache submodel
                if bill_of_processes_submodel.id not in [obj.id for obj in object_store]:
                    object_store.add(bill_of_processes_submodel)

                # Extract process list from submodel elements
                # The BillOfProcesses should contain a SubmodelElementCollection with process names
                for element in bill_of_processes_submodel.submodel_element:
                    if isinstance(element, model.SubmodelElementCollection):
                        # This is the main process collection
                        for process_element in element.value:
                            if isinstance(process_element, model.Property):
                                # Simple process name as Property value
                                product_info['processes'].append(
                                    str(process_element.value))
                        break
        except Exception as e:
            pass

        return product_info

    except Exception as e:
        print(f"Error fetching product info: {e}")
        import traceback
        traceback.print_exc()
        return None


def find_all_available_assets(aas_ids: List[str]) -> List[str]:
    """Find all available assets by recursively resolving hierarchical structures

    Args:
        asset_ids: List of AAS IDs to start from

    Returns:
        List of all AAS IDs found in the hierarchies (deduplicated, order preserved)
    """
    all_assets_ids = []
    for aas_id in aas_ids:
        try:
            # Add top level AAS
            all_assets_ids.append(aas_id)
            hierarchy_submodel = aas_client.find_submodel_by_semantic_id(
                aas_id, 'HierarchicalStructures')

            if not hierarchy_submodel:
                print(f"Warning: No HierarchicalStructures found for {aas_id}")
                continue

            resolved_assets = recursively_resolve_hierarchical_Structure(
                hierarchy_submodel)
            all_assets_ids.extend(resolved_assets)

        except Exception as e:
            print(f"Error fetching hierarchical structure for {aas_id}: {e}")
            import traceback
            traceback.print_exc()

    return all_assets_ids


def recursively_resolve_hierarchical_Structure(HierarchicalStructure: model.Submodel) -> List[str]:
    """Recursively resolve hierarchical structure to extract all AAS IDs

    Args:
        HierarchicalStructure: A HierarchicalStructures submodel

    Returns:
        List of AAS IDs found in the hierarchy
    """
    aas_ids = []

    # Safety check for None
    if HierarchicalStructure is None:
        return aas_ids

    try:
        # First, check the archetype - only process if it's "OneDown"
        archetype = None
        for element in HierarchicalStructure.submodel_element:
            if element.id_short == 'Archetype' and isinstance(element, model.Property):
                archetype = str(element.value)
                break

        # Only proceed if archetype is OneDown (downwards hierarchy)
        if archetype != 'OneDown':
            return aas_ids

        # Find the EntryNode entity
        for element in HierarchicalStructure.submodel_element:
            if element.id_short == 'EntryNode' and isinstance(element, model.Entity):
                # Process all child entities in the statements
                for statement in element.statement:
                    if isinstance(statement, model.Entity):
                        # Add this child entity's AAS ID (lookup from asset ID)
                        if statement.global_asset_id:
                            aas_id = aas_client.lookup_aas_by_asset_id(
                                statement.global_asset_id)
                            if aas_id:
                                aas_ids.append(aas_id)

                        # Check if this entity has a SameAs reference to follow recursively
                        for sub_statement in statement.statement:
                            if isinstance(sub_statement, model.ReferenceElement) and sub_statement.id_short == 'SameAs':
                                # Follow the reference to get the next hierarchical structure
                                try:
                                    # Extract the AAS ID from the reference to fetch its HierarchicalStructures
                                    # The reference points to a specific entity, but we need the parent AAS
                                    ref_keys = sub_statement.value.key
                                    submodel_id = None
                                    for key in ref_keys:
                                        if key.type == model.KeyTypes.SUBMODEL:
                                            submodel_id = key.value
                                            break

                                    if submodel_id:
                                        # Fetch the referenced submodel directly
                                        referenced_submodel = aas_client.get_submodel_by_id(
                                            submodel_id)
                                        if referenced_submodel:
                                            # Recursively resolve the referenced hierarchy
                                            child_aas_ids = recursively_resolve_hierarchical_Structure(
                                                referenced_submodel)
                                            aas_ids.extend(child_aas_ids)
                                except Exception as e:
                                    print(
                                        f"Error following SameAs reference: {e}")
                                    pass
                break

    except Exception as e:
        print(f"Error in recursively_resolve_hierarchical_Structure: {e}")
        import traceback
        traceback.print_exc()
        return aas_ids

    return aas_ids


def categorize_assets(aas_ids: List[str]) -> tuple[List[Dict[str, str]], Dict[str, str], Optional[str]]:
    """Categorize provided AAS IDs into shuttles, stations, and planar table

    Args:
        aas_ids: List of AAS IDs (strings)

    Returns:
        tuple: (shuttle_info list, station_ids dict, planar_table_id)
    """
    shuttle_info: List[Dict[str, str]] = []
    station_ids: Dict[str, str] = {}
    planar_table_id: Optional[str] = None

    for aas_id in aas_ids:
        try:
            # Fetch AAS shell using aas_client
            shell = aas_client.get_aas_by_id(aas_id)

            if not shell:
                print(f"Warning: Could not fetch AAS shell for {aas_id}")
                continue

            # Cache shell in object store
            if shell.id not in [obj.id for obj in object_store]:
                object_store.add(shell)

            asset_type = ''
            if shell.asset_information and shell.asset_information.asset_type:
                asset_type = str(shell.asset_information.asset_type).lower()

            shell_name = shell.id_short

            # TODO this should be a lookup in the ontology instead!
            # Categorize based on assetType
            # AssetType contains hierarchical classification like Resource/CPPM/UnloadingSystem/...
            if 'planarshuttle' in asset_type:
                shuttle_info.append({"aas_id": aas_id, "name": shell_name})
                print(f"  Categorized {shell_name} as shuttle")
            elif 'planartable' in asset_type:
                planar_table_id = aas_id
                print(f"  Categorized {shell_name} as planar table")
            elif any(system in asset_type for system in ['unloadingsystem', 'loadingsystem', 'dispensingsystem',
                                                         'stopperingsystem', 'qualitycontrolsystem', 'scrapingsystem']):
                # It's a station - determine which type from assetType
                # Check longer strings first to avoid substring matches (e.g., 'unloading' before 'loading')
                for op in ['Unloading', 'Loading', 'Dispensing', 'Stoppering', 'QualityControl', 'Scraping']:
                    if op.lower() + 'system' in asset_type:
                        station_ids[op] = aas_id
                        print(f"  Categorized {shell_name} as {op} station")
                        break

        except Exception as e:
            print(f"Error categorizing AAS {aas_id}: {e}")
            continue

    return shuttle_info, station_ids, planar_table_id


def load_subtree_from_file(filename: str) -> Optional[ET.Element]:
    """Load an existing subtree XML file and extract the BehaviorTree element

    Args:
        filename: Name of the XML file to load

    Returns:
        BehaviorTree Element or None
    """
    try:
        tree = ET.parse(f"../BTDescriptions/{filename}")
        root = tree.getroot()
        # Find and return the BehaviorTree element
        for child in root:
            if child.tag == "BehaviorTree":
                return child
        return None
    except Exception as e:
        print(f"Warning: Could not load {filename}: {e}")
        return None


def generate_complete_production_bt(aas_ids: Optional[List[str]] = None,
                                    product_aas_id: Optional[str] = None) -> str:
    """Generate complete self-contained production task behavior tree with all subtrees inline

    Args:
        asset_ids: List of asset IDs (stations, shuttles, planar table) to use
        product_aas_id: Product AAS ID to fetch requirements from

    Returns:
        XML string of the behavior tree
    """

    product_info = fetch_product_info(product_aas_id)

    shuttle_info, station_ids, planar_table_id = categorize_assets(
        find_all_available_assets(aas_ids))

    root = ET.Element("root")
    root.set("BTCPP_format", "4")

    # ===== Main Production Tree =====
    main_bt = ET.SubElement(root, "BehaviorTree", ID="MainTree")
    seq = ET.SubElement(main_bt, "Sequence")

    # Configure node - TODO: get actual product IDs from order
    ET.SubElement(seq, "Configure", ProductIDs="ProductA,ProductB,ProductC")

    # Reactive sequence
    reactive_seq = ET.SubElement(seq, "ReactiveSequence")

    # Planar table operational check
    fallback = ET.SubElement(reactive_seq, "Fallback")
    ET.SubElement(fallback, "Data_Condition",
                  comparison_type="equal",
                  Field="State",
                  expected_value="operational",
                  Property="PackMLState",
                  Asset=planar_table_id)

    if len(shuttle_info) > 1:
        # Parallel execution for shuttles - each shuttle processes products independently
        parallel = ET.SubElement(reactive_seq, "Parallel",
                                 failure_count="-1",
                                 success_count="1")

    # Add AsepticFilling subtree instance for each shuttle with direct AAS IDs
    for shuttle in shuttle_info:
        subtree_call = ET.SubElement(
            parallel if parallel != None else reactive_seq, "SubTree", ID="AsepticFilling")
        # Pass all necessary AAS IDs as parameters
        subtree_call.set("Xbot", shuttle["aas_id"])
        subtree_call.set("LoadingSystem", station_ids.get("Loading", ""))
        subtree_call.set("DispensingSystem", station_ids.get("Dispensing", ""))
        subtree_call.set("StopperingSystem", station_ids.get("Stoppering", ""))
        subtree_call.set("QualityControlSystem",
                         station_ids.get("QualityControl", ""))
        subtree_call.set("UnloadingSystem", station_ids.get("Unloading", ""))
        subtree_call.set("ScrapingSystem", station_ids.get("Scraping", ""))

    # ===== AsepticFilling Subtree (generic, reusable) =====
    aseptic_bt = ET.SubElement(root, "BehaviorTree", ID="AsepticFilling")
    occupy = ET.SubElement(aseptic_bt, "Occupy", Uuid="{Uuid}", Asset="{Xbot}")
    keep_running = ET.SubElement(occupy, "KeepRunningUntilEmpty",
                                 if_empty="SUCCESS",
                                 Queue="{ProductIDs}")
    reactive_seq2 = ET.SubElement(keep_running, "ReactiveSequence")

    # Shuttle operational check
    reactive_fallback = ET.SubElement(reactive_seq2, "ReactiveFallback")
    ET.SubElement(reactive_fallback, "Data_Condition",
                  comparison_type="equal",
                  Field="State",
                  expected_value="operational",
                  Property="PackMLState",
                  Asset="{Xbot}")
    ET.SubElement(reactive_fallback, "Sleep", msec="10000")

    # Main process flow
    process_fallback = ET.SubElement(reactive_seq2, "Fallback")
    seq_mem = ET.SubElement(process_fallback, "SequenceWithMemory")

    # Add operation subtrees
    for operation in product_info["processes"]:
        ET.SubElement(seq_mem, "SubTree", ID=operation)

    # Scraping as error recovery
    ET.SubElement(process_fallback, "SubTree", ID="Scraping")

    # ===== Load Operation Subtrees from existing files =====
    subtree_files = {
        "Loading": "loading.xml",
        "Dispensing": "dispensing.xml",
        "Stoppering": "stoppering.xml",
        "QualityControl": "qualityControl.xml",
        "Unloading": "unloading.xml",
        "Scraping": "scraping.xml"
    }

    for operation_id, filename in subtree_files.items():
        subtree_element = load_subtree_from_file(filename)
        if subtree_element is not None:
            root.append(subtree_element)
        else:
            print(f"Warning: Could not load {operation_id} from {filename}")

    # Convert to string with formatting
    xml_str = ET.tostring(root, encoding='unicode', method='xml')
    xml_output = '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_str

    return xml_output


def planning_process(aas_ids: Optional[List[str]] = None,
                     product_aas_id: Optional[str] = None) -> None:
    """Main planning process

    Args:
        asset_ids: List of asset IDs to use (shuttles, stations, planar table)
        product_aas_id: Product AAS ID to fetch requirements from
    """
    try:
        production_task_bt_xml = generate_complete_production_bt(
            aas_ids, product_aas_id)

        output_path = "../BTDescriptions/productionTask.xml"
        with open(output_path, 'w') as f:
            f.write(production_task_bt_xml)

    except Exception as e:
        print(f"Error in planning_process: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Example 1: Use with specific asset IDs and product
    product_aas_id = "https://smartproductionlab.aau.dk/aas/HgHAAS"

    aas_ids = [
        "https://smartproductionlab.aau.dk/aas/aauFillingLine",
    ]
    # print(find_all_available_assets(aas_ids))
    planning_process(aas_ids=aas_ids, product_aas_id=product_aas_id)
