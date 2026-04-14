from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, Literal, Optional

if TYPE_CHECKING:
    from unified_planning.plans import PolicyPlan


SolveMode = Literal["plan", "policy"]


@dataclass(frozen=True)
class SolveResult:
    """Normalized result returned by the planner facade.

    Policy-mode results wrap native UP ``PolicyPlan`` results.
    Plan-mode results wrap the UP ``PlanGenerationResult``.
    """

    mode: SolveMode
    backend_name: str
    status: str
    is_solved: bool
    policy_plan: Optional["PolicyPlan"] = None
    up_result: Optional[Any] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_up(
        cls,
        result: Any,
        *,
        backend_name: str,
        problem: Optional[Any] = None,
    ) -> "SolveResult":
        status_text = str(getattr(result, "status", "UNKNOWN"))
        solved_markers = (
            "SOLVED_SATISFICING",
            "SOLVED_OPTIMALLY",
        )
        is_solved = any(marker in status_text for marker in solved_markers)
        plan = getattr(result, "plan", None)
        is_policy_plan = (
            plan is not None
            and getattr(getattr(plan, "kind", None), "name", "") == "POLICY_PLAN"
        )
        metadata: Dict[str, Any] = {}
        if problem is not None:
            metadata["problem"] = problem
        return cls(
            mode="policy" if is_policy_plan else "plan",
            backend_name=backend_name,
            status=status_text,
            is_solved=is_solved,
            policy_plan=plan if is_policy_plan else None,
            up_result=result,
            metadata=metadata,
        )

    @property
    def is_policy(self) -> bool:
        return self.mode == "policy"

    @property
    def is_plan(self) -> bool:
        return self.mode == "plan"

    @property
    def is_strong_cyclic(self) -> bool:
        if self.policy_plan is not None:
            return bool(getattr(self.policy_plan, "is_strong_cyclic", False))
        return False

    @property
    def plan(self) -> Any:
        if self.up_result is None:
            raise TypeError("This solve result does not contain a sequential plan.")
        return self.up_result.plan

    @property
    def policy(self):
        if self.policy_plan is not None:
            return self.policy_plan.policy
        raise TypeError(
            "This solve result does not contain a policy result. "
            "Use a policy backend or inspect the sequential plan instead."
        )

    @property
    def fsaps(self):
        if self.policy_plan is not None:
            return self.policy_plan.fsaps
        raise TypeError(
            "This solve result does not contain a policy result. "
            "Use a policy backend or inspect the sequential plan instead."
        )

    def require_policy_result(self) -> Any:
        if self.policy_plan is not None:
            return self.policy_plan
        raise TypeError(
            "This solve result does not contain a policy result. "
            "Use a policy backend or inspect the sequential plan instead."
        )

    def require_plan_result(self) -> Any:
        if self.up_result is None:
            raise TypeError(
                "This solve result does not contain a UP plan result. "
                "Use a plan backend or inspect the PR2 policy instead."
            )
        return self.up_result

    def __getattr__(self, name: str) -> Any:
        if self.policy_plan is not None and hasattr(self.policy_plan, name):
            return getattr(self.policy_plan, name)
        if self.up_result is not None and hasattr(self.up_result, name):
            return getattr(self.up_result, name)
        raise AttributeError(name)