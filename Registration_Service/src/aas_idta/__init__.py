"""
aas_idta — IDTA-compliant AAS construction using aas_pydantic Pydantic models.

Users define AAS instances as JSON dicts matching the Pydantic model schema.
Pydantic validates + coerces values; builder converts to BaSyx.

Quick start::

    from src.aas_idta import build_from_dict, ResourceTypeAAS
    obj_store = build_from_dict(json.load(open("my_asset.json")))
"""

from .builder import (
    build_from_dict,
    build_from_json,
    build_resource_type_aas,
    generate_station_template,
)
from .id_injector import inject_ids
from .resource_template import ResourceTypeAAS
from . import submodel_templates as templates

__all__ = [
    "build_from_dict",
    "build_from_json",
    "build_resource_type_aas",
    "generate_station_template",
    "inject_ids",
    "ResourceTypeAAS",
    "templates",
]
