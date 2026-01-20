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
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Execute complete planning workflow and register the Process AAS.
        
        Args:
            asset_ids: List of AAS IDs of available assets (hierarchies resolved)
            product_aas_id: AAS ID of the product to produce
            
        Returns:
            Tuple of (Process AAS ID, generated config dict)
        """
        logger.info(f"Starting planning for product: {product_aas_id}")
        logger.info(f"Initial asset IDs: {asset_ids}")
        
        # Step 1: Fetch product information
        logger.info("Step 1: Fetching product information...")
        product_config = self._fetch_product_config(product_aas_id)
        if not product_config:
            raise ValueError(f"Could not fetch product AAS: {product_aas_id}")
        
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
        
        if not matching_result.is_complete:
            logger.warning(
                f"Incomplete matching! Unmatched steps: "
                f"{[s.name for s in matching_result.unmatched_steps]}"
            )
        else:
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
        
        return process_aas_id, process_config
    
    def _fetch_product_config(self, product_aas_id: str) -> Optional[Dict[str, Any]]:
        """Fetch product AAS and convert to config format"""
        try:
            shell = self.aas_client.get_aas_by_id(product_aas_id)
            if not shell:
                return None
            
            config = {
                'id': shell.id,
                'idShort': shell.id_short,
                'globalAssetId': shell.asset_information.global_asset_id if shell.asset_information else '',
                'ProductInformation': {},
                'BatchInformation': {},
                'BillOfProcesses': {'Processes': []},
                'Requirements': {}
            }
            
            # Fetch submodels
            submodels = self.aas_client.get_submodels_from_aas(product_aas_id)
            
            for submodel in submodels:
                submodel_type = self._identify_submodel_type(submodel)
                
                if submodel_type == 'BillOfProcesses':
                    config['BillOfProcesses'] = self._parse_bill_of_processes(submodel)
                elif submodel_type == 'Requirements':
                    config['Requirements'] = self._parse_requirements(submodel)
                elif submodel_type == 'ProductInformation':
                    config['ProductInformation'] = self._parse_product_info(submodel)
                elif submodel_type == 'BatchInformation':
                    config['BatchInformation'] = self._parse_batch_info(submodel)
            
            return config
            
        except Exception as e:
            logger.error(f"Error fetching product config: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _identify_submodel_type(self, submodel) -> str:
        """Identify submodel type from id_short or semantic_id"""
        id_short = submodel.id_short.lower() if submodel.id_short else ''
        
        if 'billofprocess' in id_short or 'process' in id_short:
            return 'BillOfProcesses'
        elif 'requirement' in id_short:
            return 'Requirements'
        elif 'productinfo' in id_short or 'product' in id_short:
            return 'ProductInformation'
        elif 'batchinfo' in id_short or 'batch' in id_short:
            return 'BatchInformation'
        
        return 'Unknown'
    
    def _parse_bill_of_processes(self, submodel) -> Dict[str, Any]:
        """Parse BillOfProcesses submodel into config format"""
        from basyx.aas import model
        
        result = {'Processes': [], 'semantic_id': ''}
        
        if submodel.semantic_id:
            for key in submodel.semantic_id.key:
                result['semantic_id'] = key.value
                break
        
        step_counter = 1
        for element in submodel.submodel_element:
            if isinstance(element, model.SubmodelElementList):
                # Process list of steps
                for step_elem in element.value:
                    if isinstance(step_elem, model.SubmodelElementCollection):
                        step_info = self._parse_process_step(step_elem, step_counter)
                        if step_info:
                            result['Processes'].append(step_info)
                            step_counter += 1
            elif isinstance(element, model.SubmodelElementCollection):
                # Direct collection of steps
                step_info = self._parse_process_step(element, step_counter)
                if step_info:
                    result['Processes'].append(step_info)
                    step_counter += 1
        
        return result
    
    def _parse_process_step(self, collection, step_num: int) -> Optional[Dict[str, Any]]:
        """Parse a single process step from SubmodelElementCollection"""
        from basyx.aas import model
        
        name = collection.id_short
        step_config = {
            'step': step_num,
            'semantic_id': '',
            'description': '',
            'estimatedDuration': 0.0,
            'parameters': {}
        }
        
        # Get semantic ID
        if collection.semantic_id:
            for key in collection.semantic_id.key:
                step_config['semantic_id'] = key.value
                break
        
        # Parse properties
        for elem in collection.value:
            if isinstance(elem, model.Property):
                if elem.id_short.lower() == 'step':
                    step_config['step'] = int(elem.value) if elem.value else step_num
                elif elem.id_short.lower() == 'description':
                    step_config['description'] = str(elem.value) if elem.value else ''
                elif elem.id_short.lower() in ['estimatedduration', 'duration']:
                    step_config['estimatedDuration'] = float(elem.value) if elem.value else 0.0
                elif elem.id_short.lower() == 'semantic_id':
                    step_config['semantic_id'] = str(elem.value) if elem.value else ''
        
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
    
    def _parse_product_info(self, submodel) -> Dict[str, Any]:
        """Parse ProductInformation submodel"""
        from basyx.aas import model
        
        result = {}
        for element in submodel.submodel_element:
            if isinstance(element, model.Property):
                result[element.id_short] = str(element.value) if element.value else ''
        
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
    
    def _resolve_asset_hierarchies(self, asset_ids: List[str]) -> List[str]:
        """Resolve hierarchical structures to find all available assets"""
        all_assets = []
        seen = set()
        
        for aas_id in asset_ids:
            if aas_id in seen:
                continue
            seen.add(aas_id)
            all_assets.append(aas_id)
            
            # Find hierarchical structure
            try:
                hierarchy_submodel = self.aas_client.find_submodel_by_semantic_id(
                    aas_id, 'HierarchicalStructures'
                )
                
                if hierarchy_submodel:
                    child_ids = self._resolve_hierarchy_submodel(hierarchy_submodel)
                    for child_id in child_ids:
                        if child_id not in seen:
                            seen.add(child_id)
                            all_assets.append(child_id)
                            # Recursively resolve children
                            child_children = self._resolve_asset_hierarchies([child_id])
                            for cc in child_children:
                                if cc not in seen:
                                    seen.add(cc)
                                    all_assets.append(cc)
            except Exception as e:
                logger.warning(f"Could not resolve hierarchy for {aas_id}: {e}")
        
        return all_assets
    
    def _resolve_hierarchy_submodel(self, submodel) -> List[str]:
        """Extract child AAS IDs from a HierarchicalStructures submodel"""
        from basyx.aas import model
        
        aas_ids = []
        
        try:
            # Check archetype
            archetype = None
            for element in submodel.submodel_element:
                if element.id_short in ['ArcheType', 'Archetype'] and isinstance(element, model.Property):
                    archetype = str(element.value)
                    break
            
            # Only process OneDown (children)
            if archetype != 'OneDown':
                return aas_ids
            
            # Find EntryNode
            for element in submodel.submodel_element:
                if element.id_short == 'EntryNode' and isinstance(element, model.Entity):
                    for statement in element.statement:
                        if isinstance(statement, model.Entity):
                            if statement.global_asset_id:
                                # Look up AAS ID from global asset ID
                                aas_id = self.aas_client.lookup_aas_by_asset_id(
                                    statement.global_asset_id
                                )
                                if aas_id:
                                    aas_ids.append(aas_id)
                    break
        except Exception as e:
            logger.warning(f"Error resolving hierarchy: {e}")
        
        return aas_ids
    
    def _fetch_resource_capabilities(self, asset_ids: List[str]) -> List[Dict[str, Any]]:
        """Fetch capabilities from all resource AAS"""
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
                
                # Find capabilities submodel
                submodels = self.aas_client.get_submodels_from_aas(aas_id)
                for submodel in submodels:
                    if 'capabilit' in submodel.id_short.lower():
                        # Parse capabilities
                        caps = self._parse_capabilities_submodel(submodel)
                        resource_info['capabilities'] = caps
                        break
                
                resources.append(resource_info)
                
            except Exception as e:
                logger.warning(f"Could not fetch capabilities for {aas_id}: {e}")
        
        return resources
    
    def _parse_capabilities_submodel(self, submodel) -> List[Dict[str, Any]]:
        """Parse capabilities from a submodel"""
        from basyx.aas import model
        
        capabilities = []
        
        for element in submodel.submodel_element:
            # Look for CapabilitySet
            if isinstance(element, model.SubmodelElementCollection):
                if 'capabilityset' in element.id_short.lower():
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
        """Parse a single capability container"""
        from basyx.aas import model
        
        # Find the Capability element
        cap_name = container.id_short.replace('Container', '')
        semantic_id = ''
        realized_by = None
        
        for elem in container.value:
            if isinstance(elem, model.Capability):
                cap_name = elem.id_short
                if elem.semantic_id:
                    for key in elem.semantic_id.key:
                        semantic_id = key.value
                        break
            elif isinstance(elem, model.SubmodelElementList):
                if elem.id_short == 'realizedBy':
                    for rel in elem.value:
                        if isinstance(rel, model.RelationshipElement):
                            # Extract skill name from reference
                            if rel.second:
                                for key in rel.second.key:
                                    if key.type == model.KeyTypes.SUBMODEL_ELEMENT_COLLECTION:
                                        realized_by = key.value
                                        break
        
        if cap_name:
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
