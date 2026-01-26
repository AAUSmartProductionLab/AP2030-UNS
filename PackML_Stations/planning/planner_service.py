#!/usr/bin/env python3
"""
Planner Service Module

Main orchestrator for production planning workflow:
1. Fetch product AAS and extract BillOfProcesses
2. Resolve asset hierarchies to find all available resources
3. Extract capabilities from each resource
4. Match product processes to resource capabilities
5. Generate behavior tree policy
6. Generate Process AAS configuration
7. Register Process AAS via MQTT to Registration Service
"""

import logging
import os
import json
import yaml
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field

from .capability_matcher import CapabilityMatcher, ProcessStep, MatchingResult
from .bt_generator import BTGenerator, BTGeneratorConfig
from .process_aas_generator import ProcessAASGenerator, ProcessAASConfig

logger = logging.getLogger(__name__)


@dataclass
class PlanningResult:
    """Result of the planning operation"""
    success: bool
    process_aas_id: Optional[str] = None
    product_aas_id: Optional[str] = None
    matching_result: Optional['MatchingResult'] = None
    error_message: Optional[str] = None
    process_config: Optional[Dict[str, Any]] = None
    
    def to_response_dict(self) -> Dict[str, Any]:
        """Convert to MQTT response format matching planningResponse.schema.json"""
        response = {
            'State': 'SUCCESS' if self.success else 'FAILURE',
            'ProductAasId': self.product_aas_id,
        }
        
        if self.success and self.process_aas_id:
            response['ProcessAasId'] = self.process_aas_id
        
        if self.error_message:
            response['ErrorMessage'] = self.error_message
        
        if self.matching_result:
            response['MatchingSummary'] = {
                'TotalSteps': len(self.matching_result.process_matches),
                'MatchedSteps': len(self.matching_result.process_matches) - len(self.matching_result.unmatched_steps),
                'UnmatchedSteps': len(self.matching_result.unmatched_steps),
                'AvailableMovers': len(self.matching_result.movers),
                'IsComplete': self.matching_result.is_complete
            }
            
            # Include unmatched capabilities
            if self.matching_result.unmatched_steps:
                response['UnmatchedCapabilities'] = [
                    {
                        'ProcessStep': step.name,
                        'RequiredCapability': step.semantic_id
                    }
                    for step in self.matching_result.unmatched_steps
                ]
            
            # Include matched capabilities
            matched = []
            for match in self.matching_result.process_matches:
                if match.is_matched and match.primary_resource:
                    matched.append({
                        'ProcessStep': match.process_step.name,
                        'RequiredCapability': match.process_step.semantic_id,
                        'MatchedResource': match.primary_resource.resource_name,
                        'ResourceAasId': match.primary_resource.aas_id
                    })
            if matched:
                response['MatchedCapabilities'] = matched
        
        return response


@dataclass
class PlannerConfig:
    """Configuration for the planner service"""
    # AAS server settings
    aas_server_url: str = "http://aas-env:8081"
    aas_registry_url: str = "http://aas-registry:8080"
    
    # MQTT settings for registration
    mqtt_broker: str = "hivemq-broker"
    mqtt_port: int = 1883
    registration_topic: str = "NN/Nybrovej/InnoLab/Registration/Config"
    
    # Output paths
    process_aas_output_dir: str = "../AASDescriptions/Process/configs"
    bt_output_dir: str = "../BTDescriptions"
    
    # BT settings
    bt_base_url: str = "https://aausmartproductionlab.github.io/AP2030-UNS/BTDescriptions"
    use_prebuilt_subtrees: bool = True
    
    # Debug settings
    save_intermediate_files: bool = True


class PlannerService:
    """
    Main orchestrator for production planning.
    
    Coordinates capability matching, BT generation, and AAS registration
    to create a complete production process from product requirements.
    """
    
    def __init__(
        self,
        aas_client,
        mqtt_client=None,
        config: Optional[PlannerConfig] = None
    ):
        """
        Initialize the planner service.
        
        Args:
            aas_client: AASClient instance for fetching AAS data
            mqtt_client: MQTT client for publishing registration requests
            config: Planner configuration
        """
        self.aas_client = aas_client
        self.mqtt_client = mqtt_client
        self.config = config or PlannerConfig()
        
        # Initialize sub-components
        self.capability_matcher = CapabilityMatcher(aas_client)
        self.bt_generator = BTGenerator(BTGeneratorConfig(
            subtrees_dir=self.config.bt_output_dir,
            use_prebuilt_subtrees=self.config.use_prebuilt_subtrees
        ))
        self.process_generator = ProcessAASGenerator(ProcessAASConfig(
            bt_base_url=self.config.bt_base_url
        ))
    
    def plan_and_register(
        self,
        asset_ids: List[str],
        product_aas_id: str
    ) -> PlanningResult:
        """
        Execute complete planning workflow and register the Process AAS.
        
        Args:
            asset_ids: List of AAS IDs of available assets (hierarchies resolved)
            product_aas_id: AAS ID of the product to produce
            
        Returns:
            PlanningResult with success status, process AAS ID, and matching details
        """
        logger.info(f"Starting planning for product: {product_aas_id}")
        logger.info(f"Initial asset IDs: {asset_ids}")
        
        # Step 1: Fetch product information
        logger.info("Step 1: Fetching product information...")
        product_config = self._fetch_product_config(product_aas_id)
        if not product_config:
            return PlanningResult(
                success=False,
                product_aas_id=product_aas_id,
                error_message=f"Could not fetch product AAS: {product_aas_id}"
            )
        
        # Step 2: Extract process steps and requirements
        logger.info("Step 2: Extracting process steps and requirements...")
        process_steps = self.capability_matcher.extract_process_steps(product_config)
        requirements = self.capability_matcher.extract_requirements(product_config)
        
        logger.info(f"Found {len(process_steps)} process steps: {[s.name for s in process_steps]}")
        
        # Step 3: Resolve all available assets from hierarchies
        logger.info("Step 3: Resolving asset hierarchies...")
        all_asset_ids = self._resolve_asset_hierarchies(asset_ids)
        logger.info(f"Resolved to {len(all_asset_ids)} assets")
        
        # Step 4: Fetch capabilities from all resources
        logger.info("Step 4: Fetching resource capabilities...")
        available_resources = self._fetch_resource_capabilities(all_asset_ids)
        logger.info(f"Found capabilities from {len(available_resources)} resources")
        
        # Step 5: Match capabilities
        logger.info("Step 5: Matching capabilities...")
        matching_result = self.capability_matcher.match_capabilities(
            process_steps, available_resources
        )
        
        # Check for incomplete matching - this is a failure condition
        if not matching_result.is_complete:
            unmatched_names = [s.name for s in matching_result.unmatched_steps]
            unmatched_caps = [s.semantic_id for s in matching_result.unmatched_steps]
            logger.warning(
                f"Incomplete matching! Unmatched steps: {unmatched_names}"
            )
            return PlanningResult(
                success=False,
                product_aas_id=product_aas_id,
                matching_result=matching_result,
                error_message=f"Cannot find resources for required capabilities: {', '.join(unmatched_names)}. "
                             f"Missing capability semantic IDs: {', '.join(unmatched_caps)}"
            )
        
        logger.info("All process steps matched successfully")
        logger.info(f"Found {len(matching_result.movers)} movers for parallel execution")
        
        # Step 6: Find planar table (motion system)
        planar_table_id = self._find_planar_table(available_resources)
        
        # Step 7: Generate behavior tree
        logger.info("Step 6: Generating behavior tree...")
        bt_xml = self.bt_generator.generate_production_bt(
            matching_result,
            product_config,
            planar_table_id
        )
        
        # Determine BT filename
        bt_filename = self._generate_bt_filename(product_config)
        bt_path = os.path.join(self.config.bt_output_dir, bt_filename)
        
        # Save BT for manual review/commit
        if self.config.save_intermediate_files:
            self._save_bt(bt_xml, bt_path)
            logger.info(f"Saved behavior tree to {bt_path}")
        
        # Step 8: Generate Process AAS config
        logger.info("Step 7: Generating Process AAS configuration...")
        process_config = self.process_generator.generate_config(
            matching_result,
            product_aas_id,
            product_config,
            requirements,
            bt_filename
        )
        
        process_aas_id = self.process_generator.get_aas_id(process_config)
        system_id = self.process_generator.get_system_id(process_config)
        
        # Save Process AAS config locally
        if self.config.save_intermediate_files:
            config_path = os.path.join(
                self.config.process_aas_output_dir,
                f"{system_id}.yaml"
            )
            self.process_generator.save_config(process_config, config_path)
            logger.info(f"Saved Process AAS config to {config_path}")
        
        # Step 9: Register via MQTT
        logger.info("Step 8: Registering Process AAS via MQTT...")
        self._register_via_mqtt(process_config)
        
        logger.info(f"Planning complete! Process AAS ID: {process_aas_id}")
        
        return PlanningResult(
            success=True,
            process_aas_id=process_aas_id,
            product_aas_id=product_aas_id,
            matching_result=matching_result,
            process_config=process_config
        )
    
    def _fetch_product_config(self, product_aas_id: str) -> Optional[Dict[str, Any]]:
        """Fetch product AAS and convert to config format using BaSyx SDK."""
        from basyx.aas import model
        
        try:
            shell = self.aas_client.get_aas_by_id(product_aas_id)
            if not shell:
                return None
            
            config = {
                'id': shell.id,
                'idShort': shell.id_short,
                'globalAssetId': shell.asset_information.global_asset_id if shell.asset_information else '',
                'BatchInformation': {},
                'BillOfProcesses': {'Processes': []},
                'Requirements': {}
            }
            
            # Get all submodels
            submodels = self.aas_client.get_submodels_from_aas(product_aas_id)
            logger.info(f"Found {len(submodels)} submodels for product AAS")
            for sm in submodels:
                logger.info(f"  Submodel: {sm.id_short}")
            
            # Find BillOfProcesses submodel ID and use raw JSON parsing
            # (BaSyx SDK fails to parse SubmodelElementList with idShorts due to AASd-120 constraint)
            bill_of_processes_id = None
            for sm in submodels:
                if sm.id_short and sm.id_short.lower() == 'billofprocesses':
                    bill_of_processes_id = sm.id
                    break
            
            if bill_of_processes_id:
                logger.info(f"Found BillOfProcesses submodel, fetching raw JSON...")
                bill_of_processes_raw = self.aas_client.get_submodel_raw(bill_of_processes_id)
                if bill_of_processes_raw:
                    config['BillOfProcesses'] = self._parse_bill_of_processes_raw(bill_of_processes_raw)
            else:
                logger.warning("BillOfProcesses submodel not found!")
            
            # Find Requirements submodel
            requirements = self._find_submodel(
                submodels,
                semantic_patterns=['Requirements', 'ProductionRequirements'],
                id_short_patterns=['Requirements']
            )
            if requirements:
                config['Requirements'] = self._parse_requirements(requirements)
            
            # Find BatchInformation submodel
            batch_info = self._find_submodel(
                submodels,
                semantic_patterns=['BatchInformation'],
                id_short_patterns=['BatchInformation']
            )
            if batch_info:
                config['BatchInformation'] = self._parse_batch_info(batch_info)
            
            return config
            
        except Exception as e:
            logger.error(f"Error fetching product config: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _find_submodel(self, submodels, semantic_patterns: List[str], id_short_patterns: List[str]):
        """Find a submodel by semantic_id patterns or id_short patterns."""
        # First try semantic_id matching
        for sm in submodels:
            if sm.semantic_id:
                for key in sm.semantic_id.key:
                    sem_value = key.value.lower()
                    for pattern in semantic_patterns:
                        if pattern.lower() in sem_value:
                            return sm
        
        # Then try id_short matching
        for sm in submodels:
            id_short = sm.id_short.lower() if sm.id_short else ''
            for pattern in id_short_patterns:
                if pattern.lower() == id_short:
                    return sm
        
        return None
    
    def _parse_bill_of_processes_raw(self, submodel_json: Dict[str, Any]) -> Dict[str, Any]:
        """Parse BillOfProcesses submodel from raw JSON.
        
        This is used instead of BaSyx SDK parsing because the SDK fails with
        AASd-120 constraint violation when SubmodelElementList items have idShorts.
        """
        result = {'Processes': [], 'semantic_id': ''}
        
        # Get semantic ID
        if 'semanticId' in submodel_json:
            keys = submodel_json['semanticId'].get('keys', [])
            if keys:
                result['semantic_id'] = keys[0].get('value', '')
        
        logger.info(f"Parsing BillOfProcesses from raw JSON")
        
        submodel_elements = submodel_json.get('submodelElements', [])
        logger.info(f"Raw JSON has {len(submodel_elements)} top-level elements")
        
        step_counter = 1
        for element in submodel_elements:
            model_type = element.get('modelType', '')
            id_short = element.get('idShort', '')
            logger.info(f"  Element: {id_short}, type: {model_type}")
            
            if model_type == 'SubmodelElementList':
                # Process list of steps (this is the Processes list)
                items = element.get('value', [])
                logger.info(f"    SubmodelElementList with {len(items)} items")
                for step_elem in items:
                    if step_elem.get('modelType') == 'SubmodelElementCollection':
                        step_info = self._parse_process_step_raw(step_elem, step_counter)
                        if step_info:
                            result['Processes'].append(step_info)
                            step_counter += 1
            elif model_type == 'SubmodelElementCollection':
                if id_short.lower() == 'processes':
                    # Container holding all process steps
                    items = element.get('value', [])
                    logger.info(f"    Found 'Processes' container with {len(items)} items")
                    for step_elem in items:
                        if step_elem.get('modelType') == 'SubmodelElementCollection':
                            step_info = self._parse_process_step_raw(step_elem, step_counter)
                            if step_info:
                                result['Processes'].append(step_info)
                                step_counter += 1
                else:
                    # Direct process step at top level
                    step_info = self._parse_process_step_raw(element, step_counter)
                    if step_info:
                        result['Processes'].append(step_info)
                        step_counter += 1
        
        logger.info(f"Parsed {len(result['Processes'])} processes from raw JSON")
        return result
    
    def _parse_process_step_raw(self, element: Dict[str, Any], step_num: int) -> Optional[Dict[str, Any]]:
        """Parse a single process step from raw JSON dict.
        
        Note: Per AASd-120, items in SubmodelElementList don't have idShort.
        The process name is stored in displayName (a valid Referable attribute).
        Fallback to idShort for legacy data compatibility.
        """
        # AASd-120 compliant: get name from displayName, fallback to idShort for legacy data
        name = element.get('idShort', '')
        
        # Try to get name from displayName (multi-language, prefer 'en')
        display_name = element.get('displayName', [])
        if display_name:
            # displayName is a list of {language, text} objects
            for lang_entry in display_name:
                if isinstance(lang_entry, dict):
                    if lang_entry.get('language', '').startswith('en'):
                        name = lang_entry.get('text', name)
                        break
            # If no English found, take the first one
            if not name and display_name:
                first_entry = display_name[0]
                if isinstance(first_entry, dict):
                    name = first_entry.get('text', '')
        
        step_config = {
            'step': step_num,
            'semantic_id': '',
            'process_semantic_id': '',
            'description': '',
            'estimatedDuration': 0.0,
            'parameters': {}
        }
        
        # Get process semantic ID from the element itself
        if 'semanticId' in element:
            keys = element['semanticId'].get('keys', [])
            if keys:
                step_config['process_semantic_id'] = keys[0].get('value', '')
        
        # Parse child elements
        for child in element.get('value', []):
            model_type = child.get('modelType', '')
            child_id = child.get('idShort', '').lower()
            
            if model_type == 'Property':
                if child_id == 'step':
                    step_config['step'] = int(child.get('value', step_num))
                elif child_id == 'description':
                    step_config['description'] = child.get('value', '')
                elif child_id in ['estimatedduration', 'duration']:
                    step_config['estimatedDuration'] = float(child.get('value', 0))
            elif model_type == 'ReferenceElement':
                if child_id == 'requiredcapability':
                    ref_value = child.get('value', {})
                    keys = ref_value.get('keys', [])
                    if keys:
                        step_config['semantic_id'] = keys[0].get('value', '')
            elif model_type == 'SubmodelElementCollection':
                if child_id == 'parameters':
                    step_config['parameters'] = self._parse_parameters_raw(child)
        
        # Fallback: if no RequiredCapability found, use process semantic_id
        if not step_config['semantic_id'] and step_config['process_semantic_id']:
            step_config['semantic_id'] = step_config['process_semantic_id']
        
        # If still no name, derive from semantic ID
        if not name and step_config['process_semantic_id']:
            name = step_config['process_semantic_id'].split('/')[-1]
        
        return {name: step_config}
    
    def _parse_parameters_raw(self, collection: Dict[str, Any]) -> Dict[str, Any]:
        """Parse parameters collection from raw JSON."""
        params = {}
        for child in collection.get('value', []):
            if child.get('modelType') == 'Property':
                id_short = child.get('idShort', '')
                value = child.get('value')
                if id_short:
                    params[id_short] = value
        return params

    def _parse_bill_of_processes(self, submodel) -> Dict[str, Any]:
        """Parse BillOfProcesses submodel into config format using BaSyx SDK.
        
        The BillOfProcesses contains a 'Processes' SubmodelElementCollection
        which contains individual process step collections (Loading, Dispensing, etc.)
        """
        from basyx.aas import model
        
        result = {'Processes': [], 'semantic_id': ''}
        
        if submodel.semantic_id:
            for key in submodel.semantic_id.key:
                result['semantic_id'] = key.value
                break
        
        logger.info(f"Parsing BillOfProcesses submodel: {submodel.id_short}")
        logger.info(f"Submodel has {len(list(submodel.submodel_element))} top-level elements")
        
        step_counter = 1
        for element in submodel.submodel_element:
            logger.info(f"  Element: {element.id_short}, type: {type(element).__name__}")
            if isinstance(element, model.SubmodelElementList):
                # Process list of steps
                logger.info(f"    SubmodelElementList with {len(list(element.value))} items")
                for step_elem in element.value:
                    logger.info(f"      List item: {step_elem.id_short}, type: {type(step_elem).__name__}")
                    if isinstance(step_elem, model.SubmodelElementCollection):
                        step_info = self._parse_process_step(step_elem, step_counter)
                        if step_info:
                            result['Processes'].append(step_info)
                            step_counter += 1
            elif isinstance(element, model.SubmodelElementCollection):
                # Check if this is the 'Processes' container or a direct process step
                if element.id_short.lower() == 'processes':
                    # This is the container holding all process steps
                    logger.info(f"    Found 'Processes' container with {len(list(element.value))} items")
                    for step_elem in element.value:
                        logger.info(f"      Item: {step_elem.id_short}, type: {type(step_elem).__name__}")
                        if isinstance(step_elem, model.SubmodelElementCollection):
                            step_info = self._parse_process_step(step_elem, step_counter)
                            if step_info:
                                result['Processes'].append(step_info)
                                step_counter += 1
                else:
                    # Direct process step at top level
                    step_info = self._parse_process_step(element, step_counter)
                    if step_info:
                        result['Processes'].append(step_info)
                        step_counter += 1
        
        logger.info(f"Parsed {len(result['Processes'])} processes")
        return result
    
    def _parse_process_step(self, collection, step_num: int) -> Optional[Dict[str, Any]]:
        """Parse a single process step from SubmodelElementCollection
        
        The BillOfProcesses structure from BaSyx:
        - Each process step is a SubmodelElementCollection with semantic_id for process type
        - RequiredCapability ReferenceElement points to the capability semantic ID for matching
        - Child properties include Description, EstimatedDuration, Parameters, Requirements
        
        For capability matching, we extract the RequiredCapability reference value.
        """
        from basyx.aas import model
        
        name = collection.id_short
        step_config = {
            'step': step_num,
            'semantic_id': '',
            'process_semantic_id': '',  # The process type (e.g., /Process/Loading)
            'description': '',
            'estimatedDuration': 0.0,
            'parameters': {}
        }
        
        # Get process semantic ID from the collection itself (describes the process type)
        if collection.semantic_id:
            for key in collection.semantic_id.key:
                step_config['process_semantic_id'] = key.value
                break
        
        # Parse child elements
        for elem in collection.value:
            if isinstance(elem, model.Property):
                id_short_lower = elem.id_short.lower()
                if id_short_lower == 'step':
                    step_config['step'] = int(elem.value) if elem.value else step_num
                elif id_short_lower == 'description':
                    step_config['description'] = str(elem.value) if elem.value else ''
                elif id_short_lower in ['estimatedduration', 'duration']:
                    step_config['estimatedDuration'] = float(elem.value) if elem.value else 0.0
            elif isinstance(elem, model.ReferenceElement):
                # RequiredCapability reference - this is what we use for matching
                if elem.id_short.lower() == 'requiredcapability':
                    if elem.value:
                        for key in elem.value.key:
                            step_config['semantic_id'] = key.value
                            break
            elif isinstance(elem, model.SubmodelElementCollection):
                # Parse parameters collection
                if elem.id_short.lower() == 'parameters':
                    step_config['parameters'] = self._parse_parameters_collection(elem)
        
        # Fallback: if no RequiredCapability found, use the process semantic_id
        # (for backward compatibility with older BillOfProcesses format)
        if not step_config['semantic_id'] and step_config['process_semantic_id']:
            step_config['semantic_id'] = step_config['process_semantic_id']
            logger.debug(f"Process {name}: No RequiredCapability found, falling back to process semantic_id")
        
        return {name: step_config}
    
    def _parse_requirements(self, submodel) -> Dict[str, Any]:
        """Parse Requirements submodel into config format"""
        from basyx.aas import model
        
        result = {
            'Environmental': {},
            'InProcessControl': {},
            'QualityControl': {}
        }
        
        for element in submodel.submodel_element:
            if isinstance(element, model.SubmodelElementCollection):
                category = element.id_short
                if category in result:
                    result[category] = self._parse_requirement_collection(element)
        
        return result
    
    def _parse_requirement_collection(self, collection) -> Dict[str, Any]:
        """Parse a requirement category collection"""
        from basyx.aas import model
        
        result = {}
        for elem in collection.value:
            if isinstance(elem, model.SubmodelElementCollection):
                req_config = {}
                for prop in elem.value:
                    if isinstance(prop, model.Property):
                        prop_name = prop.id_short.lower()
                        if prop_name in ['rate', 'value']:
                            req_config[prop_name] = float(prop.value) if prop.value else 0
                        elif prop_name == 'unit':
                            req_config['unit'] = str(prop.value) if prop.value else ''
                        elif prop_name == 'semantic_id':
                            req_config['semantic_id'] = str(prop.value) if prop.value else ''
                        elif prop_name == 'appliesto':
                            req_config['appliesTo'] = str(prop.value) if prop.value else ''
                
                result[elem.id_short] = req_config
        
        return result

    def _parse_batch_info(self, submodel) -> Dict[str, Any]:
        """Parse BatchInformation submodel"""
        from basyx.aas import model
        
        result = {}
        for element in submodel.submodel_element:
            if isinstance(element, model.Property):
                value = element.value
                if element.id_short in ['Quantity']:
                    result[element.id_short] = int(value) if value else 0
                else:
                    result[element.id_short] = str(value) if value else ''
        
        return result
    
    def _parse_parameters_collection(self, collection) -> Dict[str, Any]:
        """Parse a Parameters SubmodelElementCollection from a process step"""
        from basyx.aas import model
        
        params = {}
        for elem in collection.value:
            if isinstance(elem, model.Property):
                # Extract value and unit from qualifiers if present
                value = elem.value
                unit = ''
                if hasattr(elem, 'qualifier') and elem.qualifier:
                    for q in elem.qualifier:
                        if q.type == 'Unit':
                            unit = q.value
                            break
                
                params[elem.id_short] = {
                    'value': float(value) if value else 0.0,
                    'unit': unit
                }
        
        return params
    
    def _resolve_asset_hierarchies(self, asset_ids: List[str]) -> List[str]:
        """Resolve hierarchical structures to find all available assets recursively.
        
        Uses BaSyx SDK to properly follow SameAs references through
        the hierarchy tree. Also recursively resolves hierarchies of
        discovered child assets.
        """
        all_assets = []
        seen = set()
        
        # Use a queue for breadth-first traversal
        queue = list(asset_ids)
        
        while queue:
            aas_id = queue.pop(0)
            
            if aas_id in seen:
                continue
            seen.add(aas_id)
            all_assets.append(aas_id)
            
            # Find hierarchical structure submodel for this asset
            try:
                hierarchy_submodel = self.aas_client.find_submodel_by_semantic_id(
                    aas_id, 'HierarchicalStructures'
                )
                
                if hierarchy_submodel:
                    child_ids = self._resolve_hierarchy_submodel(hierarchy_submodel)
                    # Add newly discovered children to the queue for processing
                    for child_id in child_ids:
                        if child_id not in seen:
                            queue.append(child_id)
                else:
                    logger.debug(f"No HierarchicalStructures found for {aas_id}")
                    
            except Exception as e:
                logger.warning(f"Could not resolve hierarchy for {aas_id}: {e}")
                import traceback
                traceback.print_exc()
        
        return all_assets
    
    def _resolve_hierarchy_submodel(self, submodel) -> List[str]:
        """Recursively resolve hierarchical structure to extract all AAS IDs.
        
        Follows SameAs references to resolve nested hierarchies.
        """
        from basyx.aas import model
        
        aas_ids = []
        
        try:
            # Check archetype - only process "OneDown" (downward hierarchy)
            archetype = None
            for element in submodel.submodel_element:
                if element.id_short in ['ArcheType', 'Archetype'] and isinstance(element, model.Property):
                    archetype = str(element.value)
                    break
            
            if archetype != 'OneDown':
                return aas_ids
            
            # Find EntryNode entity
            for element in submodel.submodel_element:
                if element.id_short == 'EntryNode' and isinstance(element, model.Entity):
                    # Process all child entities in statements
                    for statement in element.statement:
                        if isinstance(statement, model.Entity):
                            child_aas_id = None
                            child_hierarchy_submodel_id = None
                            
                            # First, check for SameAs reference - this is more reliable
                            # as it points to the actual child's hierarchy submodel
                            for sub_statement in statement.statement:
                                if isinstance(sub_statement, model.ReferenceElement) and sub_statement.id_short == 'SameAs':
                                    if sub_statement.value:
                                        for key in sub_statement.value.key:
                                            if key.type == model.KeyTypes.SUBMODEL:
                                                child_hierarchy_submodel_id = key.value
                                                # Extract AAS ID from submodel ID pattern
                                                child_aas_id = self._extract_aas_id_from_submodel_id(
                                                    child_hierarchy_submodel_id
                                                )
                                                break
                            
                            # Fallback: try globalAssetId lookup
                            if not child_aas_id and statement.global_asset_id:
                                child_aas_id = self.aas_client.lookup_aas_by_asset_id(
                                    statement.global_asset_id
                                )
                            
                            if child_aas_id:
                                aas_ids.append(child_aas_id)
                            
                            # Follow SameAs to recursively resolve deeper hierarchies
                            if child_hierarchy_submodel_id:
                                try:
                                    referenced_submodel = self.aas_client.get_submodel_by_id(
                                        child_hierarchy_submodel_id
                                    )
                                    if referenced_submodel:
                                        child_aas_ids = self._resolve_hierarchy_submodel(referenced_submodel)
                                        aas_ids.extend(child_aas_ids)
                                except Exception as e:
                                    logger.debug(f"Could not follow SameAs reference: {e}")
                    break
                    
        except Exception as e:
            logger.warning(f"Error in _resolve_hierarchy_submodel: {e}")
            import traceback
            traceback.print_exc()
        
        return aas_ids
    
    def _extract_aas_id_from_submodel_id(self, submodel_id: str) -> Optional[str]:
        """Extract AAS ID from a submodel ID pattern.
        
        e.g., ".../instances/imaDispensingSystemAAS/HierarchicalStructures"
        -> "https://smartproductionlab.aau.dk/aas/imaDispensingSystem"
        """
        try:
            parts = submodel_id.split('/')
            if 'instances' in parts:
                idx = parts.index('instances')
                if idx + 1 < len(parts):
                    aas_id_short = parts[idx + 1]
                    # Try to find AAS by idShort pattern
                    possible_aas_ids = [
                        f"https://smartproductionlab.aau.dk/aas/{aas_id_short}",
                        f"https://smartproductionlab.aau.dk/aas/{aas_id_short.replace('AAS', '')}",
                    ]
                    for possible_id in possible_aas_ids:
                        try:
                            shell = self.aas_client.get_aas_by_id(possible_id)
                            if shell:
                                return possible_id
                        except:
                            continue
        except Exception as e:
            logger.debug(f"Could not extract AAS ID from submodel ID: {e}")
        
        return None
    
    def _fetch_resource_capabilities(self, asset_ids: List[str]) -> List[Dict[str, Any]]:
        """Fetch capabilities from all resource AAS using BaSyx SDK."""
        from basyx.aas import model
        
        resources = []
        
        for aas_id in asset_ids:
            try:
                shell = self.aas_client.get_aas_by_id(aas_id)
                if not shell:
                    continue
                
                resource_info = {
                    'aas_id': aas_id,
                    'name': shell.id_short,
                    'asset_type': shell.asset_information.asset_type if shell.asset_information else '',
                    'capabilities': []
                }
                
                # Get all submodels and find capabilities submodel
                submodels = self.aas_client.get_submodels_from_aas(aas_id)
                capabilities_submodel = self._find_submodel(
                    submodels,
                    semantic_patterns=['Capabilities', 'OfferedCapability'],
                    id_short_patterns=['OfferedCapabilityDescription', 'Capabilities']
                )
                
                if capabilities_submodel:
                    caps = self._parse_capabilities(capabilities_submodel)
                    resource_info['capabilities'] = caps
                
                resources.append(resource_info)
                
            except Exception as e:
                logger.warning(f"Could not fetch capabilities for {aas_id}: {e}")
        
        return resources
    
    def _parse_capabilities(self, submodel) -> List[Dict[str, Any]]:
        """Parse capabilities from submodel using BaSyx SDK."""
        from basyx.aas import model
        
        capabilities = []
        
        for element in submodel.submodel_element:
            if isinstance(element, model.SubmodelElementCollection):
                id_short = element.id_short.lower() if element.id_short else ''
                if 'capabilityset' in id_short:
                    # Parse each capability container
                    for cap_container in element.value:
                        if isinstance(cap_container, model.SubmodelElementCollection):
                            cap_info = self._parse_capability_container(cap_container)
                            if cap_info:
                                capabilities.append(cap_info)
                else:
                    # Direct capability container
                    cap_info = self._parse_capability_container(element)
                    if cap_info:
                        capabilities.append(cap_info)
        
        return capabilities
    
    def _parse_capability_container(self, container) -> Optional[Dict[str, Any]]:
        """Parse a single capability container using BaSyx SDK.
        
        Extracts the semantic ID directly from the Capability element for
        matching against product BillOfProcesses semantic IDs.
        """
        from basyx.aas import model
        
        cap_name = container.id_short.replace('Container', '') if container.id_short else ''
        semantic_id = None
        realized_by = None
        
        for elem in container.value:
            if isinstance(elem, model.Capability):
                # The Capability element's idShort is the actual capability name
                cap_name = elem.id_short or cap_name
                
                # Extract semantic ID from the Capability element
                if elem.semantic_id:
                    for key in elem.semantic_id.key:
                        semantic_id = key.value
                        break
                
            elif isinstance(elem, model.SubmodelElementList):
                if elem.id_short == 'realizedBy':
                    # Extract skill name from relationship
                    for rel in elem.value:
                        if isinstance(rel, model.RelationshipElement):
                            if rel.second:
                                for key in rel.second.key:
                                    if key.type == model.KeyTypes.SUBMODEL_ELEMENT_COLLECTION:
                                        realized_by = key.value
                                        break
        
        if cap_name:
            # Use extracted semantic ID, or construct fallback for backwards compatibility
            if not semantic_id:
                semantic_id = f"https://smartproductionlab.aau.dk/Capability/{cap_name}"
            
            return {
                'name': cap_name,
                'semantic_id': semantic_id,
                'realized_by': realized_by
            }
        
        return None
    
    def _find_planar_table(self, resources: List[Dict[str, Any]]) -> Optional[str]:
        """Find the planar table (motion system) from resources"""
        for resource in resources:
            asset_type = resource.get('asset_type', '').lower()
            if 'planartable' in asset_type or 'motionsystem' in asset_type:
                return resource.get('aas_id')
        return None
    
    def _generate_bt_filename(self, product_config: Dict[str, Any]) -> str:
        """Generate filename for the behavior tree"""
        product_name = product_config.get('idShort', 'unknown')
        # Clean for filename
        clean_name = ''.join(c for c in product_name if c.isalnum() or c in '-_')
        return f"production_{clean_name}.xml"
    
    def _save_bt(self, bt_xml: str, path: str) -> None:
        """Save behavior tree to file"""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            f.write(bt_xml)
    
    def _register_via_mqtt(self, config: Dict[str, Any]) -> None:
        """
        Register Process AAS via MQTT to Registration Service.
        
        The Registration Service accepts:
        1. Raw YAML content
        2. JSON with 'config' key (config as JSON object)
        3. JSON with 'configYaml' key (YAML as string)
        
        We use format #3 for clarity and to preserve YAML formatting.
        """
        if not self.mqtt_client:
            logger.warning("No MQTT client configured, skipping registration")
            return
        
        try:
            import time
            
            # Extract asset ID from config
            asset_id = self.process_generator.get_system_id(config)
            
            # Convert config to YAML string for transmission
            yaml_content = yaml.dump(config, default_flow_style=False, sort_keys=False)
            
            # Create registration message in expected format
            message = {
                'requestId': f"planner-{asset_id}-{int(time.time())}",
                'assetId': asset_id,
                'configYaml': yaml_content
            }
            
            # Publish to registration topic
            self.mqtt_client.publish(
                self.config.registration_topic,
                json.dumps(message),
                qos=2
            )
            
            logger.info(f"Published registration request for {asset_id} to {self.config.registration_topic}")
            
        except Exception as e:
            logger.error(f"Failed to register via MQTT: {e}")
            raise


def create_planner_from_env() -> PlannerService:
    """
    Create a PlannerService with configuration from environment variables.
    
    Environment variables:
        AAS_SERVER_URL: AAS server URL
        AAS_REGISTRY_URL: AAS registry URL
        MQTT_BROKER: MQTT broker hostname
        MQTT_PORT: MQTT broker port
    """
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from aas_client import AASClient
    
    config = PlannerConfig(
        aas_server_url=os.getenv("AAS_SERVER_URL", "http://aas-env:8081"),
        aas_registry_url=os.getenv("AAS_REGISTRY_URL", "http://aas-registry:8080"),
        mqtt_broker=os.getenv("MQTT_BROKER", "hivemq-broker"),
        mqtt_port=int(os.getenv("MQTT_PORT", "1883"))
    )
    
    aas_client = AASClient(config.aas_server_url, config.aas_registry_url)
    
    return PlannerService(aas_client, config=config)
