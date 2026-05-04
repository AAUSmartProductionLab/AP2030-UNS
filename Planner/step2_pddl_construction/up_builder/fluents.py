from __future__ import annotations

from typing import Any, Dict, List, Optional

def _is_symbolic_fluent(fluent: Dict[str, Any]) -> bool:
    """Return True iff ``fluent`` has no AAS-side transformation.

    Symbolic predicates are those introduced by the planner itself (e.g.
    ``step_ready`` / ``step_done`` from BoP ordering) that have no
    sensor-backed JSONata transformation. They are stored in the BT
    runtime's ``SymbolicState`` and never reach the AAS bus.
    """

    if str(fluent.get("transformation_aas_path") or "").strip():
        return False
    bindings = fluent.get("source_bindings") or []
    if bindings:
        primary = bindings[0]
        if str(primary.get("transformation_aas_path") or "").strip():
            return False
    return True


def _arg_to_object_name(
    param: Dict[str, Any],
    param_remap: Optional[Dict[int, Dict[str, Any]]] = None,
) -> Optional[str]:
    """Resolve a parsed atom param to a stable object-name string.

    Returns ``None`` when the parameter cannot be statically grounded
    (e.g. action-free parameter); the caller should skip the enclosing
    atom and emit a warning.
    """

    kind = param.get("kind")
    if kind == "object":
        name = str(param.get("name") or "")
        return name or None
    if kind == "action_param":
        idx = param.get("index")
        if isinstance(idx, int):
            if param_remap is not None:
                mapping = param_remap.get(idx)
                if mapping and mapping.get("kind") == "constant":
                    obj = str(mapping.get("object_name") or "")
                    if obj:
                        return obj
            # Free action parameter: defer grounding until the BT-build
            # step (resolve_action_execution_ref) substitutes the
            # invocation arg at index ``idx`` for this sentinel.
            return f"$param:{idx}"
        return None
    return None


def _atom_to_grounded_atom(
    atom: Dict[str, Any],
    fluent_lookup: Dict[str, Dict[str, Any]],
    *,
    value: bool,
    param_remap: Optional[Dict[int, Dict[str, Any]]] = None,
    warnings: Optional[List[str]] = None,
    context: str = "",
) -> Optional[Dict[str, Any]]:
    """Convert a parsed atom into a serialized GroundedAtom dict.

    Returns ``None`` when the atom is not symbolic or cannot be grounded.
    """

    if not isinstance(atom, dict) or atom.get("kind") != "atom":
        return None
    fluent_key = str(atom.get("fluent") or "")
    fluent = fluent_lookup.get(fluent_key)
    if not fluent or not _is_symbolic_fluent(fluent):
        return None

    args: List[str] = []
    for param in atom.get("params", []) or []:
        resolved = _arg_to_object_name(param, param_remap=param_remap)
        if resolved is None:
            if warnings is not None:
                warnings.append(
                    "Symbolic predicate '"
                    f"{fluent_key}' atom in {context or 'unknown context'} "
                    "could not be grounded (free or unresolved parameter); skipping."
                )
            return None
        args.append(resolved)
    # Lowercase predicate name to match UP's plan-output convention
    # (FluentCheck nodes derive their predicate name from the
    # lowercased plan literal, e.g. ``on(mim8_0001, planarshuttle1)``).
    return {"predicate": fluent_key.lower(), "args": args, "value": bool(value)}


def _walk_effect_term(
    term: Dict[str, Any],
    fluent_lookup: Dict[str, Dict[str, Any]],
    out: List[Dict[str, Any]],
    *,
    param_remap: Optional[Dict[int, Dict[str, Any]]] = None,
    polarity: bool = True,
    warnings: Optional[List[str]] = None,
    context: str = "",
) -> None:
    """Recursively flatten a deterministic effect sub-term into atoms.

    This walker rejects ``oneof`` because FOND outcomes are surfaced at a
    higher level by ``_symbolic_effects_for`` (each branch of a top-level
    ``oneof`` becomes an outcome in the emitted ``effects`` list). A
    nested ``oneof`` inside an ``and``/``not`` is unsupported: there is
    no FOND-outcome carrier for sub-action branches.
    """

    if not isinstance(term, dict):
        return
    kind = term.get("kind")
    if kind == "atom":
        atom = _atom_to_grounded_atom(
            term,
            fluent_lookup,
            value=polarity,
            param_remap=param_remap,
            warnings=warnings,
            context=context,
        )
        if atom is not None:
            out.append(atom)
        return
    if kind == "op":
        op = term.get("op")
        if op == "not":
            for child in term.get("children", []) or []:
                _walk_effect_term(
                    child,
                    fluent_lookup,
                    out,
                    param_remap=param_remap,
                    polarity=not polarity,
                    warnings=warnings,
                    context=context,
                )
            return
        if op == "and":
            for child in term.get("children", []) or []:
                _walk_effect_term(
                    child,
                    fluent_lookup,
                    out,
                    param_remap=param_remap,
                    polarity=polarity,
                    warnings=warnings,
                    context=context,
                )
            return
        if op == "oneof":
            if warnings is not None:
                warnings.append(
                    f"Nested 'oneof' effect in {context} is not supported; "
                    "only top-level oneOf effects map to FOND outcome branches."
                )
            return
        # Numeric / temporal / disjunctive operators are skipped — they
        # cannot be modelled as boolean SymbolicState atoms.
    return


