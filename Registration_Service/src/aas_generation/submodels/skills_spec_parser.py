"""Normalization utilities for Skills YAML configuration.

This module isolates YAML shape handling from AAS object construction.
It supports only the simplified ``pddl`` syntax used in current configs.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from ..semantic_ids import SemanticIdCatalog

PDDL_LOGIC_BASE = SemanticIdCatalog.PDDL_LOGIC_BASE
PDDL_ARITH_BASE = SemanticIdCatalog.PDDL_ARITH_BASE
PDDL_NONDET_BASE = SemanticIdCatalog.PDDL_NONDET_BASE
PDDL_TEMPORAL_BASE = SemanticIdCatalog.PDDL_TEMPORAL_BASE

LOGIC_SEMANTIC_IDS = SemanticIdCatalog.LOGIC_SEMANTIC_IDS
ARITHMETIC_SEMANTIC_IDS = SemanticIdCatalog.ARITHMETIC_SEMANTIC_IDS
NONDET_SEMANTIC_IDS = SemanticIdCatalog.NONDET_SEMANTIC_IDS
TEMPORAL_SEMANTIC_IDS = SemanticIdCatalog.TEMPORAL_SEMANTIC_IDS

CONDITION_GROUP_ALIASES = {
    "preconditions": "PreConditions",
    "precondition": "PreConditions",
    "PreConditions": "PreConditions",
    "at_start": "PreConditions",
    "start": "PreConditions",
    "pre": "PreConditions",
    "invariantconditions": "InvariantConditions",
    "InvariantConditions": "InvariantConditions",
    "over_all": "InvariantConditions",
    "invariant": "InvariantConditions",
    "postconditions": "PostConditions",
    "postcondition": "PostConditions",
    "PostConditions": "PostConditions",
    "at_end": "PostConditions",
    "end": "PostConditions",
    "post": "PostConditions",
}

EFFECT_GROUP_ALIASES = {
    "starteffects": "StartEffects",
    "StartEffects": "StartEffects",
    "at_start": "StartEffects",
    "start": "StartEffects",
    "continuouseffects": "ContinuousEffects",
    "ContinuousEffects": "ContinuousEffects",
    "continuous": "ContinuousEffects",
    "over_all": "ContinuousEffects",
    "endeffects": "EndEffects",
    "EndEffects": "EndEffects",
    "at_end": "EndEffects",
    "end": "EndEffects",
    "effect": "EndEffects",
}


def normalize_description_from_pddl(
    pddl_cfg: Dict[str, Any],
    skill_name: str = "skill",
) -> Dict[str, Any]:
    """Normalize simplified pddl syntax into skill_description shape."""
    if not isinstance(pddl_cfg, dict):
        raise ValueError(f"Invalid pddl config for {skill_name}: expected object")

    conditions_cfg = pddl_cfg.get("conditions", {})
    effects_cfg = pddl_cfg.get("effects", {})

    conditions = normalize_section_groups(
        groups_cfg=conditions_cfg,
        aliases=CONDITION_GROUP_ALIASES,
        default_group="PreConditions",
    )

    effects = normalize_section_groups(
        groups_cfg=effects_cfg,
        aliases=EFFECT_GROUP_ALIASES,
        default_group="EndEffects",
    )

    duration = _normalize_duration(pddl_cfg.get("duration"))

    explicit_requirements = pddl_cfg.get("requirements", []) or []
    inferred_requirements = _infer_requirements(
        duration=duration,
        conditions=conditions,
        effects=effects,
    )

    merged_requirements = _merge_requirements(explicit_requirements, inferred_requirements)

    return {
        "parameters": normalize_parameters(pddl_cfg.get("parameters", [])),
        "duration": duration,
        "conditions": conditions,
        "effects": effects,
        "requirements": merged_requirements,
    }


def normalize_parameters(parameters: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normalize parameter entries and accept compact aliases."""
    normalized: List[Dict[str, Any]] = []
    for idx, item in enumerate(parameters or []):
        if not isinstance(item, dict):
            continue

        name = item.get("name") or f"Parameter_{idx}"
        param: Dict[str, Any] = {"name": name}

        model_ref = _first_present(item, "ModelReference", "modelRef", "model_reference")
        external_ref = _first_present(item, "ExternalReference", "externalRef", "external_reference")

        if model_ref:
            param["ModelReference"] = model_ref
        if external_ref:
            param["ExternalReference"] = external_ref

        normalized.append(param)

    return normalized


def normalize_terms_payload(raw_terms: Any) -> List[Dict[str, Any]]:
    """Normalize any term payload into canonical term dictionaries."""
    return _ensure_term_list(raw_terms)


def normalize_section_groups(
    groups_cfg: Any,
    aliases: Dict[str, str],
    default_group: Optional[str] = None,
) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
    """Normalize section groups (conditions/effects) with aliases and fallback group."""
    if groups_cfg is None:
        return {}

    if isinstance(groups_cfg, dict):
        normalized: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
        for key, value in groups_cfg.items():
            canonical = aliases.get(str(key).lower())
            if canonical is None:
                continue
            terms = _normalize_group_terms(value)
            if terms:
                normalized[canonical] = {"terms": terms}
        return normalized

    if default_group:
        terms = _normalize_group_terms(groups_cfg)
        if terms:
            return {default_group: {"terms": terms}}

    return {}


def _ensure_term_list(raw_terms: Any) -> List[Dict[str, Any]]:
    if raw_terms is None:
        return []

    if isinstance(raw_terms, list):
        result: List[Dict[str, Any]] = []
        for term in raw_terms:
            normalized = _normalize_term(term)
            if normalized:
                result.append(normalized)
        return result

    normalized_single = _normalize_term(raw_terms)
    return [normalized_single] if normalized_single else []


def _normalize_term(node: Any) -> Dict[str, Any]:
    if isinstance(node, (int, float, bool, str)):
        return {"type": "constant", "value": node}

    if not isinstance(node, dict):
        return {}

    if _is_fluent_like_payload(node):
        return _normalize_fluent_payload(node)

    # Compact DSL: {and: [...]}, {not: {...}}, {pred: {...}}
    if len(node) == 1:
        only_key = next(iter(node.keys()))
        lowered = str(only_key).lower()
        if lowered in LOGIC_SEMANTIC_IDS:
            children = _ensure_term_list(node[only_key])
            return {
                "type": "logicalterm",
                "semantic_id": LOGIC_SEMANTIC_IDS[lowered],
                "terms": children,
            }

        if lowered in ARITHMETIC_SEMANTIC_IDS:
            return _normalize_arithmetic_term(lowered, node[only_key])

        if lowered in NONDET_SEMANTIC_IDS:
            return {
                "type": "nondeterministicterm",
                "semantic_id": NONDET_SEMANTIC_IDS[lowered],
                "terms": _ensure_term_list(node[only_key]),
            }

        if lowered == "preference":
            return _normalize_preference(node[only_key])

        if lowered in TEMPORAL_SEMANTIC_IDS:
            return {
                "type": "temporalterm",
                "semantic_id": TEMPORAL_SEMANTIC_IDS[lowered],
                "terms": _ensure_term_list(node[only_key]),
            }

        if lowered in {"const", "constant"}:
            const_payload = node[only_key]
            if isinstance(const_payload, dict):
                normalized_const = {
                    "type": "constant",
                    "value": const_payload.get("value"),
                }
                if const_payload.get("name"):
                    normalized_const["name"] = const_payload.get("name")
                return normalized_const
            return {"type": "constant", "value": const_payload}

        if lowered in {"pred", "predicate", "fluent", "function", "func"}:
            fluent = _normalize_fluent_payload(node[only_key])
            if lowered in {"function", "func"}:
                fluent["type"] = "function"
            return fluent

    raw_type = node.get("type")
    term_type = str(raw_type).lower() if raw_type else None

    if term_type in {"predicate", "fluent", "function"}:
        return _normalize_fluent_payload(node)

    if term_type in {"constant", "const"}:
        normalized_const = {"type": "constant", "value": node.get("value")}
        if node.get("name"):
            normalized_const["name"] = node.get("name")
        return normalized_const

    if term_type in {"logicalterm", "logicterm"}:
        terms = _ensure_term_list(node.get("terms", []))
        semantic_id = _extract_semantic_id(node)
        return {
            "type": "logicalterm",
            "terms": terms,
            **({"semantic_id": semantic_id} if semantic_id else {}),
        }

    if term_type in {"arithmeticterm", "arithmeticalterm"}:
        terms = _ensure_term_list(node.get("terms", []))
        semantic_id = _extract_semantic_id(node)
        if not semantic_id and node.get("operator"):
            semantic_id = ARITHMETIC_SEMANTIC_IDS.get(str(node.get("operator")).lower())
        return {
            "type": "arithmeticterm",
            "terms": terms,
            **({"semantic_id": semantic_id} if semantic_id else {}),
        }

    if term_type in {"nondeterministicterm", "nondetterm"}:
        terms = _ensure_term_list(node.get("terms", []))
        semantic_id = _extract_semantic_id(node)
        if not semantic_id and node.get("operator"):
            semantic_id = NONDET_SEMANTIC_IDS.get(str(node.get("operator")).lower())
        return {
            "type": "nondeterministicterm",
            "terms": terms,
            **({"semantic_id": semantic_id} if semantic_id else {}),
        }

    if term_type in {"temporalterm", "constraintterm", "preferenceterm"}:
        terms = _ensure_term_list(node.get("terms", []))
        semantic_id = _extract_semantic_id(node)
        if not semantic_id and node.get("operator"):
            semantic_id = TEMPORAL_SEMANTIC_IDS.get(str(node.get("operator")).lower())
        return {
            "type": "temporalterm",
            "terms": terms,
            **({"semantic_id": semantic_id} if semantic_id else {}),
            **({"name": node.get("name")} if node.get("name") else {}),
        }

    terms = _ensure_term_list(node.get("terms", []))
    semantic_id = _extract_semantic_id(node)
    if not semantic_id and term_type in LOGIC_SEMANTIC_IDS:
        semantic_id = LOGIC_SEMANTIC_IDS[term_type]

    normalized: Dict[str, Any] = {
        "type": term_type or "logicalterm",
        "terms": terms,
    }
    if semantic_id:
        normalized["semantic_id"] = semantic_id

    return normalized


def _normalize_group_terms(raw_group: Any) -> List[Dict[str, Any]]:
    """Normalize a condition/effect group with implicit top-level conjunction.

    At group level (e.g. at_start, at_end), both a plain list and
    a wrapped {and: [...]} should produce the same flat terms list.
    """
    if isinstance(raw_group, dict) and len(raw_group) == 1:
        only_key = next(iter(raw_group.keys()))
        if str(only_key).lower() == "and":
            return _ensure_term_list(raw_group[only_key])
    return _ensure_term_list(raw_group)


def _normalize_fluent_payload(payload: Any) -> Dict[str, Any]:
    if isinstance(payload, str):
        return {"type": "predicate", "TransformationReference": payload, "parameters": []}

    if not isinstance(payload, dict):
        return {"type": "predicate", "parameters": []}

    inferred_type = str(payload.get("type") or "predicate").lower()
    if inferred_type in {"func", "function"}:
        inferred_type = "function"

    normalized = {
        "type": inferred_type,
        "TransformationReference": _first_present(
            payload,
            "TransformationReference",
            "transformationReference",
            "ref",
            "transformation",
        ),
        "ExternalReference": _first_present(payload, "ExternalReference", "externalRef", "external"),
        "semantic_id": _extract_semantic_id(payload),
        "parameters": _first_present(payload, "parameters", "args") or [],
        "PreferenceReference": _first_present(payload, "PreferenceReference", "preferenceReference", "preference"),
        "description": payload.get("description"),
        "value": payload.get("value"),
    }

    return {k: v for k, v in normalized.items() if v is not None}


def _normalize_arithmetic_term(operator: str, payload: Any) -> Dict[str, Any]:
    if operator == "set":
        simplified = _normalize_boolean_set_effect(payload)
        if simplified:
            return simplified

    terms: List[Dict[str, Any]] = []

    if isinstance(payload, list):
        for item in payload:
            normalized = _normalize_term(item)
            if normalized:
                terms.append(normalized)
    elif isinstance(payload, dict):
        if "terms" in payload:
            terms = _ensure_term_list(payload.get("terms"))
        else:
            # Canonical left/right form
            if "left" in payload:
                left = _normalize_term(payload.get("left"))
                if left:
                    terms.append(left)
            if "right" in payload:
                right = _normalize_term(payload.get("right"))
                if right:
                    terms.append(right)

            # Compact effect forms with embedded fluent target + value
            if "pred" in payload:
                pred = _normalize_fluent_payload(payload.get("pred"))
                if pred:
                    terms.append(pred)
            if "function" in payload or "func" in payload:
                fn = _normalize_fluent_payload(payload.get("function") or payload.get("func"))
                if fn:
                    fn["type"] = "function"
                    terms.append(fn)
            if "value" in payload:
                terms.append({"type": "constant", "value": payload.get("value")})
    else:
        terms = _ensure_term_list(payload)

    return {
        "type": "arithmeticterm",
        "semantic_id": ARITHMETIC_SEMANTIC_IDS.get(operator),
        "terms": terms,
    }


def _normalize_boolean_set_effect(payload: Any) -> Dict[str, Any]:
    """Convert boolean set effects into predicate / not(predicate) terms.

    Example:
    - set: {pred: {...}, value: true}  -> predicate term
    - set: {pred: {...}, value: false} -> logical not(predicate)
    """
    if not isinstance(payload, dict):
        return {}

    value = payload.get("value")
    if not isinstance(value, bool):
        return {}

    target_payload = None
    target_type = "predicate"
    if "pred" in payload:
        target_payload = payload.get("pred")
    elif "predicate" in payload:
        target_payload = payload.get("predicate")
    elif "fluent" in payload:
        target_payload = payload.get("fluent")
    elif "function" in payload or "func" in payload:
        target_payload = payload.get("function") or payload.get("func")
        target_type = "function"

    if target_payload is None:
        return {}

    target = _normalize_fluent_payload(target_payload)
    if not target:
        return {}
    target["type"] = target_type

    if value:
        return target

    return {
        "type": "logicalterm",
        "semantic_id": LOGIC_SEMANTIC_IDS["not"],
        "terms": [target],
    }


def _normalize_duration(duration_cfg: Any) -> Dict[str, Any]:
    if duration_cfg is None:
        return {}

    if isinstance(duration_cfg, dict) and "terms" in duration_cfg:
        terms = _ensure_term_list(duration_cfg.get("terms"))
    else:
        terms = _ensure_term_list(duration_cfg)

    return {"terms": terms} if terms else {}


def _normalize_preference(payload: Any) -> Dict[str, Any]:
    """Normalize PDDL3 preference term.

    Accepted forms:
    - preference: {name: p1, term: {...}}
    - preference: {...term...}
    """
    if not isinstance(payload, dict):
        return {
            "type": "temporalterm",
            "semantic_id": TEMPORAL_SEMANTIC_IDS["preference"],
            "terms": _ensure_term_list(payload),
        }

    inner = payload.get("term") if "term" in payload else payload
    return {
        "type": "temporalterm",
        "semantic_id": TEMPORAL_SEMANTIC_IDS["preference"],
        "terms": _ensure_term_list(inner),
        **({"name": payload.get("name")} if payload.get("name") else {}),
    }


def _first_present(payload: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload and payload.get(key) is not None:
            return payload.get(key)
    return None


def _extract_semantic_id(payload: Dict[str, Any]) -> Any:
    return _first_present(payload, "semantic_id", "semanticId", "semantic")


def _is_fluent_like_payload(payload: Dict[str, Any]) -> bool:
    return any(
        key in payload
        for key in (
            "TransformationReference",
            "transformationReference",
            "ref",
            "transformation",
            "ExternalReference",
            "externalRef",
            "external",
        )
    )


def _merge_requirements(explicit_requirements: List[Any], inferred: List[str]) -> List[str]:
    ordered: List[str] = []
    seen: Set[str] = set()

    for req in explicit_requirements:
        req_str = str(req).strip()
        if not req_str:
            continue
        if not req_str.startswith(":"):
            req_str = f":{req_str}"
        if req_str not in seen:
            seen.add(req_str)
            ordered.append(req_str)

    for req in inferred:
        if req not in seen:
            seen.add(req)
            ordered.append(req)

    return ordered


def _infer_requirements(
    duration: Dict[str, Any],
    conditions: Dict[str, Any],
    effects: Dict[str, Any],
) -> List[str]:
    features: Set[str] = set()

    for section in (duration, *conditions.values(), *effects.values()):
        for term in section.get("terms", []) if isinstance(section, dict) else []:
            _collect_term_features(term, features)

    reqs: List[str] = [":strips", ":typing"]

    if duration.get("terms") or "temporal" in features:
        reqs.append(":durative-actions")
    if "negative" in features:
        reqs.append(":negative-preconditions")
    if "disjunction" in features:
        reqs.append(":disjunctive-preconditions")
    if "exists" in features:
        reqs.append(":existential-preconditions")
    if "forall" in features:
        reqs.append(":universal-preconditions")
    if "quantified" in features:
        reqs.append(":quantified-preconditions")
    if "conditional-effects" in features:
        reqs.append(":conditional-effects")
    if "numeric" in features:
        reqs.append(":numeric-fluents")
    if "nondeterministic" in features:
        reqs.append(":non-deterministic")
    return reqs


def _collect_term_features(term: Dict[str, Any], features: Set[str]) -> None:
    term_type = str(term.get("type", "")).lower()
    semantic_id = str(term.get("semantic_id", "")).lower()

    if term_type == "nondeterministicterm" or "oneof" in semantic_id:
        features.add("nondeterministic")
    if term_type == "temporalterm":
        features.add("temporal")
    if term_type == "arithmeticterm" or any(
        k in semantic_id for k in ["equal", "lessthan", "greaterthan", "assign", "increase", "decrease", "scale"]
    ):
        features.add("numeric")
    if term_type in {"function"}:
        features.add("numeric")
    if term_type == "logicalterm":
        if semantic_id.endswith("/not"):
            features.add("negative")
        if semantic_id.endswith("/or"):
            features.add("disjunction")
        if semantic_id.endswith("/exists"):
            features.add("exists")
            features.add("quantified")
        if semantic_id.endswith("/forall"):
            features.add("forall")
            features.add("quantified")
        if semantic_id.endswith("/when"):
            features.add("conditional-effects")

    for child in term.get("terms", []) or []:
        if isinstance(child, dict):
            _collect_term_features(child, features)


