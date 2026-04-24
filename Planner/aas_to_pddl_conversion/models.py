from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class AIPlanningSource:
    aas_id: str
    aas_name: str
    ai_planning_submodel: Dict[str, Any]


@dataclass
class PlanningCapability:
    name: str
    semantic_id: str
    resources: Dict[str, str]


@dataclass
class ActionRef:
    """Planner-side execution reference for a grounded PDDL action schema."""

    pddl_action_name: str
    source_aas_id: str
    source_aas_name: str
    action_key: str
    skill_target: str
    action_kind: str
    action_aas_path: str = ""
    transformation_aas_path: str = ""
    transformation: str = ""
    parameter_bindings: List[Dict[str, Any]] = field(default_factory=list)
    source_bindings: List[Dict[str, str]] = field(default_factory=list)
    # PR4: per-action symbolic effects for purely planner-internal predicates
    # (those whose fluent has no AAS transformation). Each entry has the
    # shape ``{"predicate": str, "args": [str, ...], "value": bool}`` with
    # arguments pre-grounded to object names.
    effects: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class PredicateRef:
    """Planner-side execution reference for a fluent/predicate schema."""

    fluent_name: str
    fluent_key: str
    source_aas_id: str
    source_aas_name: str
    fluent_aas_path: str = ""
    transformation_aas_path: str = ""
    transformation: str = ""
    param_types: List[str] = field(default_factory=list)
    source_bindings: List[Dict[str, str]] = field(default_factory=list)
    # PR4: tag predicates that have no AAS transformation. The BT runtime
    # routes FluentCheck nodes for these predicates through SymbolicState
    # instead of the JSONata/AAS path.
    is_symbolic: bool = False


@dataclass
class AIPlanningPipelineResult:
    bt_xml: str
    solve_result: Any
    bt_solve_result: Any
    warnings: List[str] = field(default_factory=list)
    capabilities: List[PlanningCapability] = field(default_factory=list)
    artifacts: Dict[str, str] = field(default_factory=dict)
    planner_metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class _ParsedSource:
    aas_id: str
    aas_name: str
    fluents: List[Dict[str, Any]] = field(default_factory=list)
    actions: List[Dict[str, Any]] = field(default_factory=list)
    objects: List[Dict[str, Any]] = field(default_factory=list)
    init_terms: List[Dict[str, Any]] = field(default_factory=list)
    goal_terms: List[Dict[str, Any]] = field(default_factory=list)
    constraints_terms: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
