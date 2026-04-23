"""Top-level planning facade.

This module is the first step toward a single public solver API built around
``unified_planning`` while keeping PR2 available for policy-style solving.

Current behavior:
- unified-planning ``Problem`` objects are solved through UP oneshot planners.
- ``backend='pr2'`` uses the UP-registered ``pr2`` engine explicitly.
- ``backend='auto'`` relies on UP factory selection based on ``problem.kind``.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Literal, Optional, Sequence


_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_VENDORED_UP_ROOT = _REPO_ROOT / "unified-planning"
if _VENDORED_UP_ROOT.exists():
    vendored_up_root = str(_VENDORED_UP_ROOT)
    if vendored_up_root not in sys.path:
        sys.path.insert(0, vendored_up_root)

from .solve_result import SolveResult


BackendName = Literal["auto", "pr2", "up"]


def solve(
    problem: Any,
    *,
    backend: BackendName = "auto",
    planner_name: Optional[str] = None,
    timeout: Optional[float] = None,
    params: Optional[Dict[str, Any]] = None,
    extra_args: Optional[Sequence[str]] = None,
    disable_object_sampling: bool = True,
    keep_files: bool = False,
) -> SolveResult:
    """Solve a planning problem through a single entrypoint.

    Parameters
    ----------
    problem
        A unified-planning ``Problem`` instance.
    backend
        ``auto`` routes deterministic problems to unified-planning and
        non-deterministic oneof problems to PR2.
    planner_name
        Optional explicit unified-planning engine name.
    timeout
        Per-solve timeout in seconds.
    params
        Planner-specific UP parameters.
    extra_args
        Extra PR2 command-line arguments.
    """
    if _looks_like_unified_planning_problem(problem):
        return _solve_unified_planning_problem(
            problem,
            backend=backend,
            planner_name=planner_name,
            timeout=timeout,
            params=params,
            extra_args=extra_args,
            disable_object_sampling=disable_object_sampling,
            keep_files=keep_files,
        )

    raise TypeError(
        "Unsupported solve() input. Pass a unified-planning Problem."
    )


def solve_from_files(
    domain_file: str | Path,
    problem_file: str | Path,
    *,
    backend: BackendName = "auto",
    planner_name: Optional[str] = None,
    timeout: Optional[float] = None,
    params: Optional[Dict[str, Any]] = None,
    extra_args: Optional[Sequence[str]] = None,
    disable_object_sampling: bool = True,
    keep_files: bool = False,
) -> SolveResult:
    """Solve from PDDL files.

    ``auto`` parses files with unified-planning and applies the same routing
    policy as ``solve()``.
    """
    if backend not in ("auto", "up", "pr2"):
        raise ValueError(f"Unsupported backend: {backend}")

    up_problem = _read_problem_with_unified_planning(domain_file, problem_file)
    return _solve_unified_planning_problem(
        up_problem,
        backend=backend,
        planner_name=planner_name,
        timeout=timeout,
        params=params,
        extra_args=extra_args,
        disable_object_sampling=disable_object_sampling,
        keep_files=keep_files,
    )


def _solve_unified_planning_problem(
    problem: Any,
    *,
    backend: BackendName,
    planner_name: Optional[str],
    timeout: Optional[float],
    params: Optional[Dict[str, Any]],
    extra_args: Optional[Sequence[str]],
    disable_object_sampling: bool,
    keep_files: bool,
) -> SolveResult:
    if backend not in ("auto", "up", "pr2"):
        raise ValueError(f"Unsupported backend: {backend}")

    up = _import_unified_planning()
    planner_kwargs: Dict[str, Any] = {"problem_kind": problem.kind}

    if backend == "pr2":
        planner_kwargs["name"] = "pr2"
    elif backend == "up" and planner_name is None:
        planner_kwargs["name"] = "aries"
    elif planner_name is not None:
        planner_kwargs["name"] = planner_name

    planner_params: Dict[str, Any] = dict(params or {})
    if backend == "pr2":
        planner_params.setdefault("disable_object_sampling", disable_object_sampling)
        planner_params.setdefault("extra_args", list(extra_args or []))
    if planner_params:
        planner_kwargs["params"] = planner_params

    solve_kwargs: Dict[str, Any] = {}
    if timeout is not None:
        solve_kwargs["timeout"] = timeout

    shortcuts_module = getattr(up, "shortcuts", None)
    if shortcuts_module is None:
        try:
            import unified_planning.shortcuts as shortcuts_module  # type: ignore
        except Exception as exc:
            raise RuntimeError(
                "Could not import unified-planning shortcuts module. "
                "Ensure unified_planning.shortcuts is available in the active environment."
            ) from exc

    with shortcuts_module.OneshotPlanner(**planner_kwargs) as planner:
        result = planner.solve(problem, **solve_kwargs)
        backend_name = getattr(planner, "name", None) or planner_name or "unified-planning"

    return SolveResult.from_up(result, backend_name=backend_name, problem=problem)


def _read_problem_with_unified_planning(domain_file: str | Path, problem_file: str | Path) -> Any:
    up = _import_unified_planning()
    reader_cls = None
    io_module = getattr(up, "io", None)
    if io_module is not None:
        reader_cls = getattr(io_module, "PDDLReader", None)

    if reader_cls is None:
        try:
            from unified_planning.io import PDDLReader as reader_cls  # type: ignore
        except Exception as exc:
            raise RuntimeError(
                "Could not import unified-planning PDDLReader. "
                "Ensure unified_planning.io is available in the active environment."
            ) from exc

    # Prefer the native UP parser first to avoid noisy AI-converter fallback
    # warnings on some nondeterministic oneof domains. If native parsing fails
    # (e.g., stricter syntax handling in specific domains), retry with the
    # reader default strategy.
    try:
        reader = reader_cls(force_up_pddl_reader=True)
        return reader.parse_problem(str(domain_file), str(problem_file))
    except TypeError:
        # Older/newer UP variants may not expose force_up_pddl_reader.
        reader = reader_cls()
        return reader.parse_problem(str(domain_file), str(problem_file))
    except Exception:
        reader = reader_cls()
        return reader.parse_problem(str(domain_file), str(problem_file))


def _looks_like_unified_planning_problem(problem: Any) -> bool:
    problem_type = type(problem)
    module_name = getattr(problem_type, "__module__", "")
    return module_name.startswith("unified_planning.") and hasattr(problem, "kind")


def _import_unified_planning():
    try:
        import unified_planning as up
    except ImportError as exc:
        raise RuntimeError(
            "unified_planning is required for the UP backend. Install it with "
            "'pip install unified-planning'."
        ) from exc
    return up



def _normalize_timeout(timeout: Optional[float]) -> Optional[int]:
    if timeout is None:
        return None
    return int(timeout)