from __future__ import annotations

from typing import Any, Dict, List, Optional

from .fluents import _walk_effect_term

def _build_effect_branches(
    terms: List[Dict[str, Any]],
    fluent_lookup: Dict[str, Dict[str, Any]],
    *,
    param_remap: Optional[Dict[int, Dict[str, Any]]] = None,
    warnings: Optional[List[str]] = None,
    context: str = "",
) -> List[Dict[str, Any]]:
    """Group an action's effect terms into FOND outcome branches.

    Layout of the returned value:
        [
            {"branch": 0, "atoms": [...]},  # always present
            {"branch": 1, "atoms": [...]},  # iff a top-level oneOf has
            ...                              # at least 2 children
        ]

    Atoms from top-level deterministic terms (``and``, ``not``, ``atom``)
    apply to *every* branch; they are duplicated into each branch so the
    runtime contract is "look up the branch by Outcome index and apply
    every atom in it".

    A top-level ``oneOf`` produces one branch per child. Multiple
    top-level ``oneOf`` terms in the same action are not supported (no
    way to carry a multi-dimensional outcome) -- the second and later
    are flattened into the first branch with a warning.
    """

    deterministic: List[Dict[str, Any]] = []
    fond_children: List[Dict[str, Any]] = []
    fond_seen = False
    for term in terms or []:
        if (
            isinstance(term, dict)
            and term.get("kind") == "op"
            and term.get("op") == "oneof"
        ):
            if fond_seen:
                if warnings is not None:
                    warnings.append(
                        f"Multiple top-level 'oneof' effects in {context} "
                        "are not supported; later ones are folded into "
                        "branch 0."
                    )
                _walk_effect_term(
                    term,
                    fluent_lookup,
                    deterministic,
                    param_remap=param_remap,
                    polarity=True,
                    warnings=warnings,
                    context=context,
                )
                continue
            fond_seen = True
            fond_children = list(term.get("children") or [])
        else:
            _walk_effect_term(
                term,
                fluent_lookup,
                deterministic,
                param_remap=param_remap,
                polarity=True,
                warnings=warnings,
                context=context,
            )

    if not fond_children:
        return [{"branch": 0, "atoms": list(deterministic)}]

    branches: List[Dict[str, Any]] = []
    for idx, child in enumerate(fond_children):
        branch_atoms: List[Dict[str, Any]] = list(deterministic)
        _walk_effect_term(
            child,
            fluent_lookup,
            branch_atoms,
            param_remap=param_remap,
            polarity=True,
            warnings=warnings,
            context=f"{context} oneOf[{idx}]",
        )
        branch_entry: Dict[str, Any] = {"branch": idx, "atoms": branch_atoms}
        if isinstance(child, dict):
            when_expr = str(child.get("when") or "").strip()
            if when_expr:
                branch_entry["when"] = when_expr
        branches.append(branch_entry)
    return branches


