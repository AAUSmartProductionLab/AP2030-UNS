from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, Literal, Optional

if TYPE_CHECKING:
    from pr2_adapter import PR2Result


SolveMode = Literal["plan", "policy"]


@dataclass(frozen=True)
class SolveResult:
    """Normalized result returned by the planner facade.

    Policy-mode results wrap ``PR2Result`` unchanged for downstream consumers.
    Plan-mode results wrap the UP ``PlanGenerationResult``.
    """

    mode: SolveMode
    backend_name: str
    status: str
    is_solved: bool
    pr2_result: Optional["PR2Result"] = None
    up_result: Optional[Any] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_pr2(
        cls,
        result: "PR2Result",
        *,
        backend_name: str = "pr2",
    ) -> "SolveResult":
        status = "SOLVED_POLICY" if result.is_solved else "UNSOLVED"
        return cls(
            mode="policy",
            backend_name=backend_name,
            status=status,
            is_solved=result.is_solved,
            pr2_result=result,
        )

    @classmethod
    def from_up(
        cls,
        result: Any,
        *,
        backend_name: str,
    ) -> "SolveResult":
        status_text = str(getattr(result, "status", "UNKNOWN"))
        solved_markers = (
            "SOLVED_SATISFICING",
            "SOLVED_OPTIMALLY",
        )
        is_solved = any(marker in status_text for marker in solved_markers)
        return cls(
            mode="plan",
            backend_name=backend_name,
            status=status_text,
            is_solved=is_solved,
            up_result=result,
        )

    @property
    def is_policy(self) -> bool:
        return self.mode == "policy"

    @property
    def is_plan(self) -> bool:
        return self.mode == "plan"

    @property
    def is_strong_cyclic(self) -> bool:
        if self.pr2_result is None:
            return False
        return self.pr2_result.is_strong_cyclic

    @property
    def plan(self) -> Any:
        if self.up_result is None:
            raise TypeError("This solve result does not contain a sequential plan.")
        return self.up_result.plan

    @property
    def policy(self):
        return self.require_policy_result().policy

    @property
    def fsaps(self):
        return self.require_policy_result().fsaps

    def require_policy_result(self) -> "PR2Result":
        if self.pr2_result is None:
            raise TypeError(
                "This solve result does not contain a PR2 policy result. "
                "Use a policy backend or inspect the sequential plan instead."
            )
        return self.pr2_result

    def require_plan_result(self) -> Any:
        if self.up_result is None:
            raise TypeError(
                "This solve result does not contain a UP plan result. "
                "Use a plan backend or inspect the PR2 policy instead."
            )
        return self.up_result

    def __getattr__(self, name: str) -> Any:
        if self.pr2_result is not None and hasattr(self.pr2_result, name):
            return getattr(self.pr2_result, name)
        if self.up_result is not None and hasattr(self.up_result, name):
            return getattr(self.up_result, name)
        raise AttributeError(name)