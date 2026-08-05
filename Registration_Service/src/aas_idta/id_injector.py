"""
Model-walking ID injector — sets id/id_short on validated Pydantic AAS instances.

Replaces the old _inject_ids heuristic-based dict pre-processing.
Uses Pydantic field annotations to distinguish:
  - Dict[str, SMC]  → keys are id_shorts, values are children
  - List[X]          → SML items
  - single SMC       → named child SMC
  - leaf Properties  → set id_short from field name

Walk order: post-validation (model instance).  No raw-dict guessing.
"""

from __future__ import annotations

import re
import typing
from typing import Any, Dict, List

from aas_pydantic.aas_model import (
    AAS, Submodel, SubmodelElementCollection,
    Identifiable, Referable, Property, ReferenceElement,
    MultiLanguageProperty, Range, RelationshipElement,
    File, Blob, Operation, Capability,
)

from .constants import BASE_URL

# Placeholders injected by id_preprocessor before validation.
_PLACEHOLDER_RE = re.compile(r"^elem\d+$")


def _should_rename_id_short(instance: Any, field_name: str) -> bool:
    """Whether to set id_short from *field_name* on *instance*.

    Renames when the current id_short is empty, is a preprocessor placeholder
    (``elemN``), or is a meaningless class-default equal to the type name
    (``Property``, ``File``, ``Blob``, ...).  Meaningful explicit/default
    id_shorts (e.g. ``Parameters``, ``X``) are preserved.
    """
    current = getattr(instance, "id_short", None)
    if not current:
        return True
    if _PLACEHOLDER_RE.match(current):
        return True
    default = type(instance).model_fields["id_short"].default
    return isinstance(default, str) and current == default and current == type(instance).__name__


def _is_aas_type(obj: Any) -> bool:
    """Check if obj is an AAS (not just any Submodel)."""
    return isinstance(obj, AAS) and hasattr(obj, "asset_type")


# ═══════════════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════════════

def inject_ids(model: Any) -> None:
    """
    Walk a validated Pydantic model instance and inject missing id/id_short.

    Mutates the model in place.  Safe to call after model_validate().
    Idempotent — already-set values are not overwritten.

    Handles:
        - AAS root: sets id from id_short if missing
        - Submodels: sets id = {aas_id}/submodels/{id_short}
        - Dict[str, SMC]: key → id_short on each child
        - List[X]: ensures id_short on each item
        - Leaf elements: id_short from field name
        - specific_asset_ids: copies serial_number/location
    """
    if isinstance(model, AAS):
        _inject_aas(model)
    elif isinstance(model, Submodel):
        _inject_submodel(model, parent_aas_id="")
    elif isinstance(model, SubmodelElementCollection):
        _inject_smc(model, parent_aas_id="")


# ═══════════════════════════════════════════════════════════════════════════════
# Internal walkers
# ═══════════════════════════════════════════════════════════════════════════════

def _inject_aas(aas: AAS) -> None:
    """Inject ids into AAS root and all submodels."""
    if not aas.id or not aas.id.startswith(BASE_URL):
        if aas.id_short:
            aas.id = f"{BASE_URL}/aas/{aas.id_short}"
    aas_id = aas.id

    # Move serial_number/location → specific_asset_ids
    _move_specific_asset_ids(aas)

    # Walk all submodel fields
    for field_name, field_info in aas.model_fields.items():
        if field_name in ("id", "id_short", "description", "display_name",
                          "asset_type", "derived_from",
                          "specific_asset_ids", "semantic_id",
                          "qualifiers", "supplemental_semantic_ids"):
            continue

        value = getattr(aas, field_name)
        if value is None:
            continue

        if isinstance(value, Submodel):
            _inject_submodel(value, parent_aas_id=aas_id,
                             field_name=field_name)
        elif isinstance(value, dict):
            _inject_dict_children(value, parent_aas_id=aas_id,
                                  field_name=field_name)
        elif isinstance(value, list):
            _inject_list_items(value, parent_aas_id=aas_id)


def _inject_submodel(
    sm: Submodel,
    parent_aas_id: str = "",
    field_name: str = "",
) -> None:
    """Inject ids into a Submodel and its children."""
    # Set id_short from field name if missing/placeholder
    if field_name and _should_rename_id_short(sm, field_name):
        sm.id_short = field_name
    # Set id from parent
    if (not sm.id or not sm.id.startswith(BASE_URL)) and parent_aas_id:
        sm.id = f"{parent_aas_id}/submodels/{sm.id_short}"

    submodel_id = sm.id

    for child_field_name, child_field_info in sm.model_fields.items():
        if child_field_name in ("id", "id_short", "description", "display_name",
                                "semantic_id", "qualifiers",
                                "supplemental_semantic_ids"):
            continue

        value = getattr(sm, child_field_name)
        if value is None:
            continue

        if isinstance(value, SubmodelElementCollection):
            _inject_smc(value, parent_aas_id=submodel_id,
                        field_name=child_field_name)
        elif isinstance(value, dict):
            _inject_dict_children(value, parent_aas_id=submodel_id,
                                  field_name=child_field_name)
        elif isinstance(value, list):
            _inject_list_items(value, parent_aas_id=submodel_id)
        elif isinstance(value, (Property, ReferenceElement,
                                 MultiLanguageProperty, Range,
                                 File, Blob)):
            _inject_leaf(value, field_name=child_field_name)


def _inject_smc(
    smc: SubmodelElementCollection,
    parent_aas_id: str = "",
    field_name: str = "",
) -> None:
    """Inject ids into an SMC and its children."""
    if field_name and _should_rename_id_short(smc, field_name):
        smc.id_short = field_name

    for child_field_name, child_field_info in smc.model_fields.items():
        if child_field_name in ("id_short", "description", "display_name",
                                "semantic_id", "qualifiers",
                                "supplemental_semantic_ids"):
            continue

        value = getattr(smc, child_field_name)
        if value is None:
            continue

        if isinstance(value, SubmodelElementCollection):
            _inject_smc(value, parent_aas_id=parent_aas_id,
                        field_name=child_field_name)
        elif isinstance(value, dict):
            _inject_dict_children(value, parent_aas_id=parent_aas_id,
                                  field_name=child_field_name)
        elif isinstance(value, list):
            _inject_list_items(value, parent_aas_id=parent_aas_id)
        elif isinstance(value, (Property, ReferenceElement,
                                 MultiLanguageProperty, Range,
                                 File, Blob)):
            _inject_leaf(value, field_name=child_field_name)


def _inject_dict_children(
    d: Dict[str, Any],
    parent_aas_id: str = "",
    field_name: str = "",
) -> None:
    """Walk Dict[str, SMC] values — key becomes id_short."""
    for key, value in d.items():
        if value is None:
            continue
        if isinstance(value, SubmodelElementCollection):
            if _should_rename_id_short(value, key):
                value.id_short = key
            _inject_smc(value, parent_aas_id=parent_aas_id,
                        field_name=key)
        elif isinstance(value, dict):
            # Nested dict-of-dict — rare, but handle
            _inject_dict_children(value, parent_aas_id=parent_aas_id,
                                  field_name=key)
        elif isinstance(value, (Property, ReferenceElement,
                                 MultiLanguageProperty, Range,
                                 File, Blob)):
            _inject_leaf(value, field_name=key)


def _inject_list_items(
    lst: List[Any],
    parent_aas_id: str = "",
) -> None:
    """Walk list items — each may be an SMC, leaf, or nested collection."""
    for item in lst:
        if item is None:
            continue
        if isinstance(item, SubmodelElementCollection):
            _inject_smc(item, parent_aas_id=parent_aas_id,
                        field_name="")
        elif isinstance(item, dict):
            for key, value in item.items():
                if isinstance(value, SubmodelElementCollection):
                    _inject_smc(value, parent_aas_id=parent_aas_id,
                                field_name=key)
        elif isinstance(item, (Property, ReferenceElement,
                                MultiLanguageProperty, Range,
                                File, Blob)):
            pass  # List items without id_short are fine (SML semantics)


def _inject_leaf(
    element: Any,
    field_name: str = "",
) -> None:
    """Inject id_short on a leaf AAS element if missing/placeholder/type-default."""
    if field_name and _should_rename_id_short(element, field_name):
        element.id_short = field_name


def _move_specific_asset_ids(aas: AAS) -> None:
    """Move top-level serial_number/location into specific_asset_ids."""
    sids = getattr(aas, 'specific_asset_ids', None) or {}
    serial = getattr(aas, 'serial_number', None)
    location = getattr(aas, 'location', None)

    if serial and 'serialNumber' not in sids:
        sids['serialNumber'] = serial
    if location and 'location' not in sids:
        sids['location'] = location

    if sids:
        aas.specific_asset_ids = sids
