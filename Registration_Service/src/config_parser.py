"""
Asset Config — load JSON, validate against ResourceTypeAAS, extract runtime configs.

The Pydantic model IS the config.  JSON must match the ResourceTypeAAS schema.
id_short and id are auto-injected post-validation via the id_injector module.

Usage::

    from src.config_parser import parse_config_file, extract_operation_delegation_entry

    asset = parse_config_file("my_asset.json")
    topics = extract_operation_delegation_entry(asset)
"""

from __future__ import annotations

import json
import logging
from typing import Dict, List, Any

from .aas_idta.resource_template.asset import ResourceTypeAAS
from .aas_idta.id_injector import inject_ids

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Load & validate
# ═══════════════════════════════════════════════════════════════════════════════

def parse_config_file(path: str) -> ResourceTypeAAS:
    """Load JSON config file, validate, inject IDs, return ResourceTypeAAS."""
    with open(path) as f:
        return parse_config_data(json.load(f))


def parse_config_data(data: Dict[str, Any]) -> ResourceTypeAAS:
    """Validate against ResourceTypeAAS, inject IDs, return model instance."""
    asset = ResourceTypeAAS.model_validate(data)
    inject_ids(asset)
    return asset


# ═══════════════════════════════════════════════════════════════════════════════
# Extraction — read from typed Pydantic model fields
# ═══════════════════════════════════════════════════════════════════════════════

def extract_mqtt_endpoint(asset: ResourceTypeAAS) -> Dict[str, Any]:
    aid = asset.asset_interfaces_description
    if aid is None:
        return {"broker_host": None, "broker_port": 1883, "base_topic": None}
    iface = _g(aid.submodel_element, "interface_mqtt")
    if iface is None:
        return {"broker_host": None, "broker_port": 1883, "base_topic": None}
    ep = _g(iface.value, "endpoint_metadata")
    if ep is None:
        return {"broker_host": None, "broker_port": 1883, "base_topic": None}
    base_prop = _g(ep.value, "base")
    base_val = _v(base_prop)
    result = {"broker_host": None, "broker_port": 1883, "base_topic": None, "broker_url": base_val}
    if base_val:
        url = base_val
        if url.startswith("mqtt://"):
            url = url[7:]
        if "/" in url:
            host_port, topic = url.split("/", 1)
            result["base_topic"] = topic.rstrip("/")
            if ":" in host_port:
                h, p = host_port.split(":", 1)
                result["broker_host"] = h
                result["broker_port"] = int(p)
            else:
                result["broker_host"] = host_port
        else:
            result["broker_host"] = url
    return result


def _aid_actions(asset: ResourceTypeAAS):
    aid = asset.asset_interfaces_description
    if aid is None:
        return None, None
    iface = _g(aid.submodel_element, "interface_mqtt")
    if iface is None:
        return None, None
    imd = _g(iface.value, "interaction_metadata")
    if imd is None:
        return None, None
    ep = extract_mqtt_endpoint(asset)
    return imd, ep


def extract_actions(asset: ResourceTypeAAS) -> List[Dict[str, Any]]:
    imd, ep = _aid_actions(asset)
    if imd is None:
        return []
    actions_container = _g(imd.value, "actions")
    if actions_container is None:
        return []
    base_topic = ep.get("base_topic", "")
    actions = []
    for a in actions_container.value.values():
        key = _v(_g(a.value, "key")) or "action"
        forms = _g(a.value, "forms")
        resp = _g(forms.value, "response") if forms else None
        cmd_href = _v(_g(forms.value, "href")) if forms else f"/CMD/{key}"
        cmd_topic = f"{base_topic}/{cmd_href.lstrip('/')}" if base_topic else cmd_href.lstrip("/")
        has_resp = resp is not None or bool(_v(_g(a.value, "output_schema")))
        resp_topic = None
        if has_resp and resp:
            resp_href = _v(_g(resp.value, "href")) if resp else f"/DATA/{key}"
            resp_topic = f"{base_topic}/{resp_href.lstrip('/')}" if base_topic else resp_href.lstrip("/")
        sync_str = (_v(_g(a.value, "synchronous")) or "true").lower()
        actions.append({
            "name": key, "key": key, "title": _v(_g(a.value, "title")) or key,
            "command_topic": cmd_topic, "response_topic": resp_topic,
            "input_schema": _v(_g(a.value, "input_schema")), "output_schema": _v(_g(a.value, "output_schema")),
            "has_response": has_resp, "is_one_way": not has_resp,
            "synchronous": sync_str == "true",
            "qos": int(_v(_g(forms.value, "mqv_qos"))) if (forms and _v(_g(forms.value, "mqv_qos"))) else 2,
            "retain": (_v(_g(forms.value, "mqv_retain")) if forms else "false") == "true",
        })
    return actions


def extract_properties(asset: ResourceTypeAAS) -> List[Dict[str, Any]]:
    imd, ep = _aid_actions(asset)
    if imd is None:
        return []
    props_container = _g(imd.value, "properties")
    if props_container is None:
        return []
    base_topic = ep.get("base_topic", "")
    props = []
    for p in props_container.value.values():
        key = _v(_g(p.value, "key")) or "property"
        forms = _g(p.value, "forms")
        href = _v(_g(forms.value, "href")) if forms else f"/DATA/{key}"
        topic = f"{base_topic}/{href.lstrip('/')}" if base_topic else href.lstrip("/")
        props.append({
            "name": key, "key": key, "title": _v(_g(p.value, "title")) or key,
            "topic": topic, "schema": _v(_g(p.value, "output_schema")),
            "qos": int(_v(_g(forms.value, "mqv_qos"))) if (forms and _v(_g(forms.value, "mqv_qos"))) else 0,
            "retain": (_v(_g(forms.value, "mqv_retain")) if forms else "false") == "true",
        })
    return props


def extract_operation_delegation_entry(asset: ResourceTypeAAS) -> Dict[str, Any]:
    ep = extract_mqtt_endpoint(asset)
    actions = extract_actions(asset)
    skills = {}
    for a in actions:
        entry = {"command_topic": a["command_topic"]}
        if a.get("input_schema"):
            entry["input_schema"] = a["input_schema"]
        if not a["is_one_way"]:
            entry["response_topic"] = a["response_topic"]
            entry["synchronous"] = a["synchronous"]
        if a.get("qos"):
            entry["qos"] = a["qos"]
        skills[a["name"]] = entry
    return {
        "base_topic": ep.get("base_topic", ""),
        "submodel_id": f"{asset.id}/submodels/AssetInterfacesDescription" if asset.id else "",
        "skills": skills,
    }


def extract_databridge_property_mappings(asset: ResourceTypeAAS) -> List[Dict[str, Any]]:
    properties = extract_properties(asset)
    variables = _extract_variables(asset)
    mappings = []
    for var in variables:
        iface_name = var.get("interface_reference")
        field = var.get("field")
        if iface_name:
            for prop in properties:
                if prop["name"] == iface_name:
                    mappings.append({
                        "variable_name": var["name"],
                        "mqtt_topic": prop["topic"],
                        "mqtt_field": field,
                        "value_fields": [field] if field else [],
                        "schema_url": prop.get("schema"),
                    })
                    break
    return mappings


def _extract_variables(asset: ResourceTypeAAS) -> List[Dict[str, Any]]:
    vm = asset.variables
    if vm is None:
        return []
    result = []
    for v in vm.submodel_element.values():
        iface = _g(v.value, "interface_reference")
        result.append({
            "name": v.id_short,
            "semantic_id": _v(_g(v.value, "semantic_id_param")) if v.value else "",
            "interface_reference": _v(_g(iface.value, "name")) if iface else None,
            "field": _v(_g(iface.value, "field")) if iface else None,
        })
    return result


def _g(obj, name, default=None):
    """Read a child from a values model (attribute) or Dict container (key)."""
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _v(prop) -> str:
    """Safely extract .value from a Property, returning '' for None."""
    try:
        return prop.value
    except AttributeError:
        return ""
