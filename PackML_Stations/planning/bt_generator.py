#!/usr/bin/env python3
"""
Behavior Tree Generator Module

Generates behavior tree XML for production processes based on 
capability matching results and pre-built subtree files.
"""

import logging
import os
from xml.etree import ElementTree as ET
from xml.dom import minidom
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from .capability_matcher import MatchingResult, ProcessStep, MoverInfo, CapabilityMatch

logger = logging.getLogger(__name__)


@dataclass
class BTGeneratorConfig:
    """Configuration for behavior tree generation"""
    subtrees_dir: str = "../BTDescriptions"
    use_prebuilt_subtrees: bool = True
    include_error_recovery: bool = True
    tree_nodes_model_file: str = "tree_nodes_model.xml"
    # Map process names to subtree files
    subtree_file_mapping: Dict[str, str] = None
    # Map process/capability names to actual subtree IDs
    subtree_id_mapping: Dict[str, str] = None

    def __post_init__(self):
        if self.subtree_file_mapping is None:
            self.subtree_file_mapping = {
                "Loading": "loading.xml",
                "Dispensing": "dispensing.xml",
                "Stoppering": "stoppering.xml",
                "QualityControl": "qualityControl.xml",
                "Inspection": "qualityControl.xml",  # Alias
                "Unloading": "unloading.xml",
                "Scraping": "scraping.xml",
                "Capping": "capping.xml",
                # Standard subtrees that were previously included via <include>
                # "LineSOP": "lineSOP.xml",
                # "PlanarSOP": "planarSOP.xml",
                "Product": "product.xml",
            }
        if self.subtree_id_mapping is None:
            # Map capability/process names to actual subtree IDs
            self.subtree_id_mapping = {
                "Inspection": "QualityControl",  # Inspection capability uses QualityControl subtree
                "inspection": "QualityControl",
            }


class BTGenerator:
    """
    Generates behavior tree XML for production processes.

    Supports:
    - Using pre-built subtree files for standard operations
    - Generating custom subtrees from capability matches
    - Configuring parallelism based on mover count
    - Including error recovery subtrees
    """

    def __init__(self, config: Optional[BTGeneratorConfig] = None):
        """
        Initialize the BT generator.

        Args:
            config: Generator configuration
        """
        self.config = config or BTGeneratorConfig()
        # Store capability matches for asset lookup
        self._capability_assets: Dict[str, List[str]] = {}

    def _format_assets_array(self, aas_ids: List[str]) -> str:
        """
        Format a list of AAS IDs as a BT++ array string.

        Args:
            aas_ids: List of AAS ID strings

        Returns:
            Formatted array string like "aas1;aas2;aas3"
        """
        return ";".join(aas_ids)

    def _build_capability_assets_map(self, matching_result: MatchingResult) -> None:
        """
        Build a mapping from capability/process names to all matching asset IDs.

        Args:
            matching_result: Result from capability matching
        """
        self._capability_assets.clear()

        # Map each process step to all its matched resources
        for match in matching_result.process_matches:
            step_name = match.process_step.name
            asset_ids = [res.aas_id for res in match.matched_resources]
            self._capability_assets[step_name] = asset_ids
            # Also store with capitalized name
            self._capability_assets[self._get_subtree_id(
                step_name)] = asset_ids

        # Add movers as "Moving" capability
        mover_ids = [m.aas_id for m in matching_result.movers]
        self._capability_assets["Moving"] = mover_ids
        self._capability_assets["Xbot"] = mover_ids

        # For Scraping/Unloading, use all unloading-capable resources
        # Check if we have explicit unloading matches, otherwise use all resources
        if "Unloading" not in self._capability_assets:
            # Use all station resources as potential unloading points
            all_station_ids = []
            for match in matching_result.process_matches:
                all_station_ids.extend(
                    [res.aas_id for res in match.matched_resources])
            self._capability_assets["Unloading"] = list(set(all_station_ids))
            self._capability_assets["Scraping"] = self._capability_assets["Unloading"]

        logger.debug(f"Built capability assets map: {self._capability_assets}")

    def get_assets_for_capability(self, capability_name: str) -> List[str]:
        """
        Get all asset IDs that match a capability.

        Args:
            capability_name: Name of the capability (e.g., "Loading", "Moving")

        Returns:
            List of AAS IDs
        """
        return self._capability_assets.get(capability_name, [])

    def generate_production_bt(
        self,
        matching_result: MatchingResult,
        product_info: Dict[str, Any],
        planar_table_id: Optional[str] = None
    ) -> str:
        """
        Generate a complete production behavior tree.

        Args:
            matching_result: Result from capability matching
            product_info: Product information dictionary
            planar_table_id: AAS ID of the planar table (motion system)

        Returns:
            Complete BT XML as string
        """
        # Build capability to assets mapping first
        self._build_capability_assets_map(matching_result)

        root = ET.Element("root")
        root.set("BTCPP_format", "4")
        root.set("main_tree_to_execute", "Production")

        # Generate main production tree
        self._generate_main_tree(
            root, matching_result, product_info, planar_table_id
        )

        # Generate AsepticFilling subtree
        self._generate_aseptic_filling_tree(root, matching_result)

        # Load and embed pre-built subtrees directly (no includes)
        if self.config.use_prebuilt_subtrees:
            self._append_prebuilt_subtrees(root, matching_result)

        # Append TreeNodesModel for node type definitions
        self._append_tree_nodes_model(root)

        # Format and return XML
        return self._format_xml(root)

    def _generate_main_tree(
        self,
        root: ET.Element,
        matching_result: MatchingResult,
        product_info: Dict[str, Any],
        planar_table_id: Optional[str]
    ) -> None:
        """Generate the main Production behavior tree"""
        main_bt = ET.SubElement(root, "BehaviorTree", ID="Production")
        seq = ET.SubElement(main_bt, "Sequence")

        # Configure node - initialize product queue
        ET.SubElement(seq, "Configure", ProductIDs="{ProductIDs}")

        # Reactive sequence for main production flow
        reactive_seq = ET.SubElement(seq, "ReactiveSequence")

        # Planar table operational check with SOP fallback
        # if planar_table_id:
        #     # fallback = ET.SubElement(reactive_seq, "Fallback")
        #     ET.SubElement(reactive_seq, "Data_Condition",
        #                   comparison_type="equal",
        #                   Field="State",
        #                   expected_value="operational",
        #                   Property="PackMLState",
        #                   Asset=planar_table_id)
        # ET.SubElement(fallback, "SubTree",
        #               ID="PlanarSOP",
        #               Asset="Operator",
        #               _autoremap="true")

        # Parallel execution for movers
        movers = matching_result.movers
        parallelism = matching_result.parallelism_factor

        if parallelism > 1:
            parallel = ET.SubElement(reactive_seq, "Parallel",
                                     failure_count="-1",
                                     success_count="1")

            # Add AsepticFilling subtree for each mover
            for i, mover in enumerate(movers):
                ET.SubElement(parallel, "SubTree",
                              ID="AsepticFilling",
                              Xbot=f"{{Xbot{i+1}}}",
                              ProductID="",
                              _autoremap="true")
        else:
            # Single mover case
            if movers:
                ET.SubElement(reactive_seq, "SubTree",
                              ID="AsepticFilling",
                              Xbot="{Xbot1}",
                              ProductID="",
                              _autoremap="true")

    def _generate_aseptic_filling_tree(
        self,
        root: ET.Element,
        matching_result: MatchingResult
    ) -> None:
        """Generate the AsepticFilling subtree that processes one product"""
        aseptic_bt = ET.SubElement(root, "BehaviorTree", ID="AsepticFilling")

        # Occupy the mover for exclusive use - use Assets array with all movers
        mover_assets = self._format_assets_array(
            self.get_assets_for_capability("Moving"))
        occupy = ET.SubElement(aseptic_bt, "Occupy",
                               Uuid="{Uuid}",
                               Assets=mover_assets)

        # Keep running until product queue is empty
        keep_running = ET.SubElement(occupy, "KeepRunningUntilEmpty",
                                     if_empty="SUCCESS",
                                     Queue="{ProductIDs}")

        reactive_seq = ET.SubElement(keep_running, "ReactiveSequence")

        # Mover operational check - use SelectedAsset from Occupy
        reactive_fallback = ET.SubElement(reactive_seq, "ReactiveFallback")
        ET.SubElement(reactive_fallback, "Data_Condition",
                      comparison_type="equal",
                      Field="State",
                      expected_value="operational",
                      Property="PackMLState",
                      Asset="{SelectedAsset}")
        ET.SubElement(reactive_fallback, "Sleep", msec="10000")

        # Main process flow with error recovery
        process_fallback = ET.SubElement(reactive_seq, "Fallback")

        # Only create SequenceWithMemory if there are process steps to add
        if matching_result.process_matches:
            seq_mem = ET.SubElement(process_fallback, "SequenceWithMemory")

            # Add subtree call for each process step
            for match in matching_result.process_matches:
                step = match.process_step
                subtree_id = self._get_subtree_id(step.name)

                # Add the subtree call with Assets array of all matching resources
                subtree_elem = ET.SubElement(seq_mem, "SubTree", ID=subtree_id)

                # Pass all matched resources as Assets array
                if match.matched_resources:
                    assets_array = self._format_assets_array(
                        [res.aas_id for res in match.matched_resources]
                    )
                    subtree_elem.set("Assets", assets_array)

                # Also pass mover reference
                subtree_elem.set("Xbot", "{SelectedAsset}")
                subtree_elem.set("_autoremap", "true")

        # Error recovery: Scraping - use unloading-capable resources
        if self.config.include_error_recovery:
            scraping_subtree = ET.SubElement(
                process_fallback, "SubTree", ID="Scraping")
            unload_assets = self.get_assets_for_capability("Unloading")
            if unload_assets:
                scraping_subtree.set(
                    "Assets", self._format_assets_array(unload_assets))
            scraping_subtree.set("Xbot", "{SelectedAsset}")
            scraping_subtree.set("_autoremap", "true")

    def _get_subtree_id(self, process_name: str) -> str:
        """Get the subtree ID for a process name"""
        # First check if there's a direct mapping for this process name
        if process_name in self.config.subtree_id_mapping:
            return self.config.subtree_id_mapping[process_name]

        # Capitalize first letter
        capitalized = process_name[0].upper(
        ) + process_name[1:] if process_name else process_name

        # Check if the capitalized version has a mapping
        if capitalized in self.config.subtree_id_mapping:
            return self.config.subtree_id_mapping[capitalized]

        return capitalized

    def _append_prebuilt_subtrees(
        self,
        root: ET.Element,
        matching_result: MatchingResult
    ) -> None:
        """Load and embed pre-built subtree files directly into the BT XML"""
        loaded_subtrees = set()

        # Collect all needed subtree names
        needed_subtrees = set()
        for match in matching_result.process_matches:
            subtree_id = self._get_subtree_id(match.process_step.name)
            needed_subtrees.add(subtree_id)

        # Always include Scraping for error recovery
        if self.config.include_error_recovery:
            needed_subtrees.add("Scraping")

        # Always include standard subtrees that were previously referenced via <include>
        # needed_subtrees.add("LineSOP")
        # needed_subtrees.add("PlanarSOP")
        needed_subtrees.add("Product")

        # Track loaded files to avoid loading the same file multiple times
        loaded_files = set()

        # Load each needed subtree
        for subtree_id in needed_subtrees:
            if subtree_id in loaded_subtrees:
                continue

            filename = self.config.subtree_file_mapping.get(subtree_id)
            if not filename:
                # Try lowercase
                filename = self.config.subtree_file_mapping.get(
                    subtree_id.lower())

            if filename:
                # Skip if we already loaded this file (it may contain multiple subtrees)
                if filename in loaded_files:
                    loaded_subtrees.add(subtree_id)
                    continue

                subtree_elements = self._load_subtree_from_file(filename)
                if subtree_elements:
                    for subtree_element in subtree_elements:
                        root.append(subtree_element)
                        # Mark the ID of this subtree as loaded
                        bt_id = subtree_element.get("ID", "")
                        if bt_id:
                            loaded_subtrees.add(bt_id)
                    loaded_files.add(filename)
                    loaded_subtrees.add(subtree_id)
                    logger.debug(
                        f"Loaded {len(subtree_elements)} subtree(s) from {filename}")
                else:
                    logger.warning(
                        f"Could not load subtree {subtree_id} from {filename}")
            else:
                logger.warning(f"No subtree file mapping for {subtree_id}")

    def _load_subtree_from_file(self, filename: str) -> List[ET.Element]:
        """Load all subtrees from an XML file (a file may contain multiple BehaviorTree elements)"""
        try:
            filepath = os.path.join(self.config.subtrees_dir, filename)
            tree = ET.parse(filepath)
            root = tree.getroot()

            # Find and return all BehaviorTree elements
            subtrees = []
            for child in root:
                if child.tag == "BehaviorTree":
                    subtrees.append(child)

            return subtrees if subtrees else []
        except Exception as e:
            logger.warning(f"Could not load {filename}: {e}")
            return []

    def _append_tree_nodes_model(self, root: ET.Element) -> None:
        """Load and append the TreeNodesModel from the model file"""
        try:
            filepath = os.path.join(
                self.config.subtrees_dir,
                self.config.tree_nodes_model_file
            )
            tree = ET.parse(filepath)
            model_root = tree.getroot()

            # Find and append the TreeNodesModel element
            for child in model_root:
                if child.tag == "TreeNodesModel":
                    root.append(child)
                    logger.debug(f"Loaded TreeNodesModel from {filepath}")
                    return

            logger.warning(f"No TreeNodesModel found in {filepath}")
        except Exception as e:
            logger.warning(f"Could not load TreeNodesModel: {e}")

    def _format_xml(self, root: ET.Element) -> str:
        """Format XML with proper indentation"""
        xml_str = ET.tostring(root, encoding='unicode', method='xml')

        # Use minidom for pretty printing
        try:
            dom = minidom.parseString(xml_str)
            pretty_xml = dom.toprettyxml(indent="  ")

            # Remove extra blank lines and fix declaration
            lines = pretty_xml.split('\n')
            filtered_lines = [line for line in lines if line.strip()]

            # Ensure proper XML declaration
            if filtered_lines and filtered_lines[0].startswith('<?xml'):
                filtered_lines[0] = '<?xml version="1.0" encoding="UTF-8"?>'
            else:
                filtered_lines.insert(
                    0, '<?xml version="1.0" encoding="UTF-8"?>')

            return '\n'.join(filtered_lines)
        except Exception as e:
            logger.warning(f"Could not pretty-print XML: {e}")
            return '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_str

    def generate_process_subtree(
        self,
        process_step: ProcessStep,
        resource_aas_id: str,
        mover_param: str = "{Xbot}"
    ) -> ET.Element:
        """
        Generate a custom subtree for a single process step.

        This is used when no pre-built subtree exists.

        Args:
            process_step: The process step to generate for
            resource_aas_id: AAS ID of the resource
            mover_param: Blackboard parameter for mover

        Returns:
            BehaviorTree Element
        """
        bt = ET.Element(
            "BehaviorTree", ID=self._get_subtree_id(process_step.name))

        # Standard pattern: Occupy -> ReactiveSequence -> Move + Execute
        # Use Assets (array) - will be filled by caller or from blackboard
        occupy = ET.SubElement(bt, "Occupy",
                               Uuid="{ProductID}",
                               Assets="{Assets}",
                               _skipIf="scrap == true")

        reactive_seq = ET.SubElement(occupy, "ReactiveSequence")

        # Operational check - use SelectedAsset output from Occupy
        reactive_fallback = ET.SubElement(reactive_seq, "ReactiveFallback")
        ET.SubElement(reactive_fallback, "Data_Condition",
                      comparison_type="equal",
                      Field="State",
                      expected_value="operational",
                      Property="PackMLState",
                      Asset="{SelectedAsset}")
        ET.SubElement(reactive_fallback, "Sleep", msec="10000")

        # Execution sequence
        exec_seq = ET.SubElement(reactive_seq, "Sequence")

        # Move to station - get station position from selected asset
        ET.SubElement(exec_seq, "moveToPosition",
                      Uuid="{ProductID}",
                      TargetPosition="{Station}",
                      Asset="{Xbot}")

        # Execute operation on the selected asset
        operation_name = process_step.name.lower()
        ET.SubElement(exec_seq, "Command_Execution",
                      Parameters="'{}'",
                      Uuid="{ProductID}",
                      Operation=operation_name,
                      Asset="{SelectedAsset}")

        return bt

    def get_blackboard_parameters(
        self,
        matching_result: MatchingResult,
        planar_table_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get the blackboard parameters that need to be initialized.

        Note: With the new Assets array approach, most parameters are 
        embedded directly in the BT XML. This method returns supplementary
        parameters that may still be needed.

        Args:
            matching_result: Capability matching result
            planar_table_id: Optional planar table AAS ID

        Returns:
            Dict mapping parameter names to their values (strings or lists)
        """
        # Build capability map if not already built
        if not self._capability_assets:
            self._build_capability_assets_map(matching_result)

        params: Dict[str, Any] = {}

        # Add planar table
        if planar_table_id:
            params["PlanarTable"] = planar_table_id

        # Add all capability asset mappings
        for capability_name, asset_ids in self._capability_assets.items():
            params[f"{capability_name}Assets"] = asset_ids

        return params
