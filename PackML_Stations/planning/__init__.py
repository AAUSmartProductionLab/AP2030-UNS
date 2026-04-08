"""
Production Planning Package

This package provides modular components for production planning:
- Capability matching between product requirements and resource capabilities
- Behavior tree generation for production processes
- Process AAS generation and registration

Usage:
    from planning import PlannerService, PlannerConfig, PlanningResult
    
    planner = PlannerService(aas_client, mqtt_client, PlannerConfig())
    result = planner.plan_and_register(asset_ids, product_aas_id)
    if result.success:
        print(f"Created Process AAS: {result.process_aas_id}")
    else:
        print(f"Planning failed: {result.error_message}")
"""

from .capability_matcher import CapabilityMatcher
from .bt_generator import BTGenerator
from .process_aas_generator import ProcessAASGenerator
from .planner_service import PlannerService, PlannerConfig, PlanningResult

__all__ = [
    'CapabilityMatcher',
    'BTGenerator',
    'ProcessAASGenerator',
    'PlannerService',
    'PlannerConfig',
]
