#!/usr/bin/env python3
"""
Capability Matcher Module

Matches product BillOfProcesses requirements to available resource capabilities
using semantic ID matching.
"""

import logging
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ProcessStep:
    """Represents a single process step from the product's BillOfProcesses"""
    name: str
    step: int
    semantic_id: str
    description: str = ""
    estimated_duration: float = 0.0
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ResourceCapability:
    """Represents a capability offered by a resource"""
    name: str
    semantic_id: str
    aas_id: str
    resource_name: str
    realized_by: Optional[str] = None  # Skill that realizes this capability
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CapabilityMatch:
    """Result of matching a process step to a resource capability"""
    process_step: ProcessStep
    matched_resources: List[ResourceCapability]  # Can have multiple matches
    is_matched: bool = False
    
    def __post_init__(self):
        self.is_matched = len(self.matched_resources) > 0
    
    @property
    def primary_resource(self) -> Optional[ResourceCapability]:
        """Get the first matched resource (primary assignment)"""
        return self.matched_resources[0] if self.matched_resources else None


@dataclass
class MoverInfo:
    """Information about a mover (shuttle) resource"""
    aas_id: str
    name: str
    asset_type: str


@dataclass 
class MatchingResult:
    """Complete result of capability matching"""
    process_matches: List[CapabilityMatch]
    movers: List[MoverInfo]
    unmatched_steps: List[ProcessStep]
    all_resources: List[ResourceCapability]
    
    @property
    def is_complete(self) -> bool:
        """Check if all process steps have at least one match"""
        return len(self.unmatched_steps) == 0
    
    @property
    def parallelism_factor(self) -> int:
        """Suggested number of parallel production subtrees based on mover count"""
        return max(1, len(self.movers))


class CapabilityMatcher:
    """
    Matches product process requirements to available resource capabilities.
    
    Uses semantic ID matching to find resources that can fulfill each
    step in the product's BillOfProcesses.
    """
    
    # Known mover asset type patterns (for determining parallelism)
    MOVER_PATTERNS = [
        'planarshuttle',
        'shuttle',
        'mover',
        'agv',
        'amr',
        'xbot'
    ]
    
    # Known station asset type patterns
    STATION_PATTERNS = [
        'loadingsystem',
        'unloadingsystem', 
        'dispensingsystem',
        'stopperingsystem',
        'qualitycontrolsystem',
        'scrapingsystem',
        'weighingsystem',
        'inspectionsystem',
        'cappingsystem'
    ]
    
    def __init__(self, aas_client):
        """
        Initialize the capability matcher.
        
        Args:
            aas_client: AASClient instance for fetching AAS data
        """
        self.aas_client = aas_client
    
    def match_capabilities(
        self,
        process_steps: List[ProcessStep],
        available_resources: List[Dict[str, Any]]
    ) -> MatchingResult:
        """
        Match process steps to available resource capabilities.
        
        Args:
            process_steps: Ordered list of process steps from product BillOfProcesses
            available_resources: List of resource info dicts with capabilities
                Each dict should have: aas_id, name, asset_type, capabilities
                
        Returns:
            MatchingResult with all matches, movers, and unmatched steps
        """
        # Extract all capabilities from resources
        all_capabilities: List[ResourceCapability] = []
        movers: List[MoverInfo] = []
        
        for resource in available_resources:
            aas_id = resource.get('aas_id', '')
            name = resource.get('name', '')
            asset_type = resource.get('asset_type', '').lower()
            
            # Check if this is a mover
            if self._is_mover(asset_type):
                movers.append(MoverInfo(
                    aas_id=aas_id,
                    name=name,
                    asset_type=asset_type
                ))
            
            # Extract capabilities
            for cap in resource.get('capabilities', []):
                all_capabilities.append(ResourceCapability(
                    name=cap.get('name', ''),
                    semantic_id=cap.get('semantic_id', ''),
                    aas_id=aas_id,
                    resource_name=name,
                    realized_by=cap.get('realized_by'),
                    properties=cap.get('properties', {})
                ))
        
        # Match each process step
        process_matches: List[CapabilityMatch] = []
        unmatched_steps: List[ProcessStep] = []
        
        for step in process_steps:
            matched_resources = self._find_matching_capabilities(
                step.semantic_id, all_capabilities
            )
            
            match = CapabilityMatch(
                process_step=step,
                matched_resources=matched_resources
            )
            process_matches.append(match)
            
            if not match.is_matched:
                unmatched_steps.append(step)
                logger.warning(
                    f"No resource found for process step '{step.name}' "
                    f"with semantic ID: {step.semantic_id}"
                )
        
        return MatchingResult(
            process_matches=process_matches,
            movers=movers,
            unmatched_steps=unmatched_steps,
            all_resources=all_capabilities
        )
    
    def _find_matching_capabilities(
        self,
        semantic_id: str,
        capabilities: List[ResourceCapability]
    ) -> List[ResourceCapability]:
        """
        Find all capabilities that match a given semantic ID.
        
        Matching strategy:
        1. Exact match (preferred)
        2. Exact match on final path segment (e.g., /Loading matches /Loading)
        
        Args:
            semantic_id: The semantic ID to match
            capabilities: List of available capabilities
            
        Returns:
            List of matching ResourceCapability objects
        """
        exact_matches = []
        segment_matches = []
        
        # Extract the final path segment from target
        target_segment = semantic_id.rstrip('/').split('/')[-1].lower()
        
        for cap in capabilities:
            cap_semantic = cap.semantic_id.strip() if cap.semantic_id else ''
            
            # Skip empty semantic IDs
            if not cap_semantic:
                continue
            
            # Check exact match (case-insensitive)
            if cap_semantic.lower() == semantic_id.lower():
                exact_matches.append(cap)
                continue
            
            # Check final path segment match
            cap_segment = cap_semantic.rstrip('/').split('/')[-1].lower()
            if cap_segment == target_segment:
                segment_matches.append(cap)
        
        # Prefer exact matches, fall back to segment matches
        return exact_matches if exact_matches else segment_matches
    
    def _normalize_semantic_id(self, semantic_id: str) -> str:
        """Normalize semantic ID for comparison"""
        return semantic_id.lower().strip().rstrip('/')
    
    def _is_mover(self, asset_type: str) -> bool:
        """Check if asset type indicates a mover/shuttle"""
        asset_type_lower = asset_type.lower()
        return any(pattern in asset_type_lower for pattern in self.MOVER_PATTERNS)
    
    def _is_station(self, asset_type: str) -> bool:
        """Check if asset type indicates a station"""
        asset_type_lower = asset_type.lower()
        return any(pattern in asset_type_lower for pattern in self.STATION_PATTERNS)
    
    def extract_process_steps(self, product_config: Dict[str, Any]) -> List[ProcessStep]:
        """
        Extract process steps from a product AAS configuration.
        
        Args:
            product_config: Product AAS configuration dictionary
            
        Returns:
            Ordered list of ProcessStep objects
        """
        steps = []
        
        bill_of_processes = product_config.get('BillOfProcesses', {})
        processes = bill_of_processes.get('Processes', [])
        
        for process_entry in processes:
            # Handle both dict format {Name: {...}} and list format
            if isinstance(process_entry, dict):
                for process_name, process_config in process_entry.items():
                    if isinstance(process_config, dict):
                        steps.append(ProcessStep(
                            name=process_name,
                            step=process_config.get('step', len(steps) + 1),
                            semantic_id=process_config.get('semantic_id', ''),
                            description=process_config.get('description', ''),
                            estimated_duration=process_config.get('estimatedDuration', 0.0),
                            parameters=process_config.get('parameters', {})
                        ))
        
        # Sort by step number
        steps.sort(key=lambda s: s.step)
        
        return steps
    
    def extract_requirements(self, product_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract requirements from a product AAS configuration.
        
        Args:
            product_config: Product AAS configuration dictionary
            
        Returns:
            Dictionary of requirements organized by type
        """
        requirements = product_config.get('Requirements', {})
        
        result = {
            'environmental': {},
            'in_process_control': {},
            'quality_control': {},
            'error_recovery': {}
        }
        
        # Environmental requirements
        for key, value in requirements.get('Environmental', {}).items():
            if isinstance(value, dict):
                result['environmental'][key] = value
        
        # In-process controls
        for key, value in requirements.get('InProcessControl', {}).items():
            if isinstance(value, dict):
                result['in_process_control'][key] = {
                    'semantic_id': value.get('semantic_id', ''),
                    'applies_to': value.get('appliesTo', ''),
                    'rate': value.get('rate', 100),
                    'unit': value.get('unit', '%'),
                    'description': value.get('description', '')
                }
        
        # Quality control
        for key, value in requirements.get('QualityControl', {}).items():
            if isinstance(value, dict) and 'rate' in value:
                result['quality_control'][key] = {
                    'semantic_id': value.get('semantic_id', ''),
                    'applies_to': value.get('appliesTo', ''),
                    'rate': value.get('rate', 100),
                    'unit': value.get('unit', '%'),
                    'description': value.get('description', ''),
                    'sample_size': value.get('sampleSize')
                }
        
        # Error recovery
        error_recovery = product_config.get('ErrorRecovery', {})
        for key, value in error_recovery.items():
            if isinstance(value, dict):
                result['error_recovery'][key] = {
                    'semantic_id': value.get('semantic_id', ''),
                    'description': value.get('description', ''),
                    'triggered_by': value.get('triggeredBy', [])
                }
        
        return result
