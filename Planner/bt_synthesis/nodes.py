"""
Behavior Tree node types for BehaviorTree.CPP v4.

Pure data-structure definitions — no PDDL dependencies, no conversion
logic.  Every other module in the pipeline imports node types from here.

Node hierarchy
--------------
::

    BTNode
    ├── ConditionNode        — succeeds iff a fluent holds
    ├── ActionNode           — executes a grounded action
    ├── ForbiddenActionNode  — marker for FSAP-forbidden actions
    ├── SuccessLeaf          — always succeeds (goal reached)
    ├── FailureLeaf          — always fails
    ├── SubTreeRef           — reference to a parameterized template
    ├── Sequence             — non-reactive sequence (resume on RUNNING)
    ├── ReactiveSelector     — reactive fallback (tries children L→R)
    ├── ReactiveSequence     — reactive sequence (re-checks from first)
    ├── Inverter             — decorator: SUCCESS ↔ FAILURE
    └── KeepRunningUntilFailure — decorator: SUCCESS/RUNNING -> RUNNING

Extras
------
- ``WorldState`` — minimal fluent store for standalone tick execution.
- ``BehaviorTree`` — thin wrapper that owns a root node + template map.
- Naming helpers used during tree construction.
"""

from __future__ import annotations

import re
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set, Tuple


# ===================================================================
#  Tick status
# ===================================================================


class Status(Enum):
    """Tick return status."""

    SUCCESS = auto()
    FAILURE = auto()
    RUNNING = auto()


# ===================================================================
#  Base class
# ===================================================================


class BTNode:
    """Base class for behavior-tree nodes.

    Parameters
    ----------
    name : str
        Human-readable label (also used for XML ``name`` attribute).
    is_rule_leaf : bool
        When ``True`` the node is treated as an extractable subtree
        definition during XML serialization.
    """

    def __init__(self, name: str = "", *, is_rule_leaf: bool = False):
        self.name = name
        self.is_rule_leaf = is_rule_leaf

    def tick(self, world: "WorldState") -> Status:
        raise NotImplementedError

    def pretty(self, indent: int = 0) -> str:
        return " " * indent + f"[{self.__class__.__name__}] {self.name}"


# ===================================================================
#  Leaf nodes
# ===================================================================


class ConditionNode(BTNode):
    """Succeeds iff a literal currently holds in the world state."""

    def __init__(self, fluent: str, execution_ref: Optional[Dict[str, Any]] = None):
        super().__init__(fluent)
        self.fluent = fluent
        self.execution_ref: Dict[str, Any] = dict(execution_ref or {})

    def tick(self, world: "WorldState") -> Status:
        return Status.SUCCESS if world.holds(self.fluent) else Status.FAILURE

    def pretty(self, indent: int = 0) -> str:
        return " " * indent + f"[Condition] {self.fluent}"


class ActionNode(BTNode):
    """Executes an action via ``world.execute_action(...)``."""

    def __init__(self, action_name: str, execution_ref: Optional[Dict[str, Any]] = None):
        super().__init__(action_name)
        self.action_name = action_name
        self.execution_ref: Dict[str, Any] = dict(execution_ref or {})

    def tick(self, world: "WorldState") -> Status:
        return world.execute_action(self.action_name)

    def pretty(self, indent: int = 0) -> str:
        return " " * indent + f"[Action] {self.action_name}"


class ForbiddenActionNode(BTNode):
    """Marker leaf for a forbidden action (FSAP dispatch point).

    Always returns FAILURE so the parent Fallback tries the next branch.
    """

    def __init__(self, forbidden_action: str):
        super().__init__(f"Forbid:{forbidden_action}")
        self.forbidden_action = forbidden_action

    def tick(self, world: "WorldState") -> Status:
        return Status.FAILURE

    def pretty(self, indent: int = 0) -> str:
        return " " * indent + f"[Forbid] {self.forbidden_action}"


class SuccessLeaf(BTNode):
    """Always succeeds and marks the goal as reached."""

    def __init__(self):
        super().__init__("GoalReached")

    def tick(self, world: "WorldState") -> Status:
        world.goal_reached = True
        return Status.SUCCESS

    def pretty(self, indent: int = 0) -> str:
        return " " * indent + "[Success] GoalReached"


class FailureLeaf(BTNode):
    """Always fails."""

    def __init__(self, name: str = "Fail"):
        super().__init__(name)

    def tick(self, world: "WorldState") -> Status:
        return Status.FAILURE


class SubTreeRef(BTNode):
    """Reference to a parameterized subtree template.

    Rendered as ``<SubTree ID="template_id" arg0="val0" .../>``.
    """

    def __init__(self, template_id: str, params: Dict[str, str]):
        super().__init__(template_id)
        self.template_id = template_id
        self.params = params  # {param_name: concrete_value}

    def tick(self, world: "WorldState") -> Status:
        return Status.FAILURE  # not executed directly

    def pretty(self, indent: int = 0) -> str:
        ps = ", ".join(f"{k}={v}" for k, v in self.params.items())
        return " " * indent + f"[SubTree] {self.template_id}({ps})"


# ===================================================================
#  Composite / decorator nodes
# ===================================================================


class ReactiveSelector(BTNode):
    """Reactive fallback — tries children left-to-right each tick."""

    def __init__(
        self,
        name: str,
        children: List[BTNode],
        *,
        is_rule_leaf: bool = False,
    ):
        super().__init__(name, is_rule_leaf=is_rule_leaf)
        self.children = children

    def tick(self, world: "WorldState") -> Status:
        for child in self.children:
            status = child.tick(world)
            if status != Status.FAILURE:
                return status
        return Status.FAILURE

    def pretty(self, indent: int = 0) -> str:
        lines = [" " * indent + f"[?] {self.name}"]
        for child in self.children:
            lines.append(child.pretty(indent + 4))
        return "\n".join(lines)


class ReactiveSequence(BTNode):
    """Reactive sequence — re-checks from the first child every tick."""

    def __init__(
        self,
        name: str,
        children: List[BTNode],
        *,
        is_rule_leaf: bool = False,
    ):
        super().__init__(name, is_rule_leaf=is_rule_leaf)
        self.children = children

    def tick(self, world: "WorldState") -> Status:
        for child in self.children:
            status = child.tick(world)
            if status != Status.SUCCESS:
                return status
        return Status.SUCCESS

    def pretty(self, indent: int = 0) -> str:
        lines = [" " * indent + f"[→] {self.name}"]
        for child in self.children:
            lines.append(child.pretty(indent + 4))
        return "\n".join(lines)


class Sequence(BTNode):
    """Non-reactive sequence.

    Unlike ReactiveSequence, this node resumes from the last RUNNING child
    on the next tick instead of restarting from the first child.
    """

    def __init__(
        self,
        name: str,
        children: List[BTNode],
        *,
        is_rule_leaf: bool = False,
    ):
        super().__init__(name, is_rule_leaf=is_rule_leaf)
        self.children = children
        self._running_index = 0

    def tick(self, world: "WorldState") -> Status:
        while self._running_index < len(self.children):
            status = self.children[self._running_index].tick(world)
            if status == Status.SUCCESS:
                self._running_index += 1
                continue
            if status == Status.RUNNING:
                return Status.RUNNING
            self._running_index = 0
            return Status.FAILURE

        self._running_index = 0
        return Status.SUCCESS

    def pretty(self, indent: int = 0) -> str:
        lines = [" " * indent + f"[=>] {self.name}"]
        for child in self.children:
            lines.append(child.pretty(indent + 4))
        return "\n".join(lines)


class Inverter(BTNode):
    """Decorator that swaps SUCCESS ↔ FAILURE."""

    def __init__(self, child: BTNode):
        super().__init__("Inverter")
        self.child = child

    def tick(self, world: "WorldState") -> Status:
        s = self.child.tick(world)
        if s == Status.SUCCESS:
            return Status.FAILURE
        if s == Status.FAILURE:
            return Status.SUCCESS
        return s

    def pretty(self, indent: int = 0) -> str:
        lines = [" " * indent + "[¬] Inverter"]
        lines.append(self.child.pretty(indent + 4))
        return "\n".join(lines)


class KeepRunningUntilFailure(BTNode):
    """Decorator that runs until child failure.

    - child FAILURE -> FAILURE
    - child SUCCESS -> RUNNING
    - child RUNNING -> RUNNING
    """

    def __init__(self, child: BTNode, name: str = "KeepRunningUntilFailure"):
        super().__init__(name)
        self.child = child

    def tick(self, world: "WorldState") -> Status:
        s = self.child.tick(world)
        if s == Status.FAILURE:
            return Status.FAILURE
        return Status.RUNNING

    def pretty(self, indent: int = 0) -> str:
        lines = [" " * indent + "[↻] KeepRunningUntilFailure"]
        lines.append(self.child.pretty(indent + 4))
        return "\n".join(lines)


# ===================================================================
#  Minimal world state (for standalone tick execution / debugging)
# ===================================================================


class WorldState:
    """Minimal world state for standalone BT execution.

    Fluents are stored as positive atoms (strings).
    Negation is expressed as ``not(atom)``.
    """

    def __init__(self, fluents: Optional[Set[str]] = None):
        self.fluents: Set[str] = fluents or set()
        self.goal_reached: bool = False

    def holds(self, literal: str) -> bool:
        if literal.startswith("not(") and literal.endswith(")"):
            return literal[4:-1] not in self.fluents
        return literal in self.fluents

    def execute_action(self, action_name: str) -> Status:
        return Status.SUCCESS


# ===================================================================
#  BehaviorTree wrapper
# ===================================================================


class BehaviorTree:
    """Thin wrapper that drives tick-based execution of a root node."""

    def __init__(self, root: BTNode):
        self.root = root
        # Parameterized subtree templates: template_id -> (template_tree, [param_names])
        self.templates: Dict[str, Tuple[BTNode, List[str]]] = {}

    def tick(self, world: WorldState) -> Status:
        return self.root.tick(world)

    def run(
        self,
        world: WorldState,
        max_ticks: int = 1000,
        on_tick: Optional[Callable[[int, Status, WorldState], None]] = None,
    ) -> bool:
        for i in range(max_ticks):
            status = self.tick(world)
            if on_tick:
                on_tick(i, status, world)
            if world.goal_reached:
                return True
            if status == Status.FAILURE:
                return False
        return False

    def pretty(self) -> str:
        return self.root.pretty()


# ===================================================================
#  Naming helpers (used by bt_builder, bt_optimize, bt_xml)
# ===================================================================


def sanitize_bt_id(name: str) -> str:
    """Turn a node name into a safe BehaviorTree ID string."""
    safe = []
    for ch in name:
        if ch.isalnum() or ch in {"_", "-"}:
            safe.append(ch)
        elif ch.isspace():
            safe.append("_")
    return "".join(safe).strip("_") or "SubTree"


def to_camel_case(snake: str) -> str:
    """Convert a snake_case string to CamelCase.

    >>> to_camel_case("release_shuttle")
    'ReleaseShuttle'
    """
    return "".join(w.capitalize() for w in snake.split("_") if w)


def readable_action_id(action: str) -> str:
    """Build a human-readable, XML-safe ID from a grounded action string.

    Examples::

        'move shuttle0 parking1 loader1 p0'  → 'Move_shuttle0_parking1_loader1_p0'
        'occupy_shuttle shuttle0 p0 slot0'   → 'OccupyShuttle_shuttle0_p0_slot0'
    """
    parts = action.split()
    if not parts:
        return sanitize_bt_id(action)
    action_type = to_camel_case(parts[0])
    if len(parts) == 1:
        return action_type
    return sanitize_bt_id(action_type + "_" + "_".join(parts[1:]))
