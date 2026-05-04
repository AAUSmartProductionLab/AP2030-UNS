from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class AIPlanningSource:
    aas_id: str
    aas_name: str
    ai_planning_submodel: Dict[str, Any]
    asset_type: str = ""


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
