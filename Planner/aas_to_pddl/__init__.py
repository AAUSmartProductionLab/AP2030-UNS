"""
Production Planning Package

This package provides modular components for production planning:
- AIPlanning extraction and model merging across product/resources
- Unified Planning / PR2 solve with BT policy conversion
- Process AAS generation and registration

Usage:
    from aas_to_pddl import PlannerService, PlannerConfig, PlanningResult
    
    planner = PlannerService(aas_client, mqtt_client, PlannerConfig())
    result = planner.plan_and_register(asset_ids, product_aas_id)
    if result.success:
        print(f"Created Process AAS: {result.process_aas_id}")
    else:
        print(f"Planning failed: {result.error_message}")
"""

from .core.process_aas_generator import ProcessAASGenerator
from .core.planner_service import PlannerService, PlannerConfig, PlanningResult

__all__ = [
    'ProcessAASGenerator',
    'PlannerService',
    'PlannerConfig',
    'PlanningResult',
]
