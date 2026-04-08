"""
MQTT Schema Parser for Operation Delegation Service

Parses JSON schemas (including $ref) to automatically determine:
- Required fields
- Array structures
- Field types and defaults

This allows the operation delegation service to automatically construct
MQTT messages according to their schemas without hardcoding mappings.
"""

import json
import logging
import os
from typing import Dict, Any, List, Tuple
from urllib.parse import urlparse
import requests

logger = logging.getLogger(__name__)


class SchemaParser:
    """
    Parses JSON schemas to determine message structure.
    
    Handles:
    - Local file schemas
    - Remote URL schemas (with caching)
    - Schema references ($ref)
    - allOf, anyOf, oneOf constructs
    - Array types with prefixItems
    """
    
    def __init__(self, local_schema_dir: str = None, cache_ttl: int = 3600):
        """
        Initialize schema parser.
        
        Args:
            local_schema_dir: Directory containing local schema files
            cache_ttl: Time to live for cached remote schemas (seconds)
        """
        self.local_schema_dir = local_schema_dir or os.path.join(
            os.path.dirname(__file__), "..", "..", "MQTTSchemas"
        )
        self.cache: Dict[str, Dict] = {}
        self.cache_ttl = cache_ttl
        
    def parse_schema(self, schema_url: str) -> Dict[str, Any]:
        """
        Parse a schema and resolve all references.
        
        Args:
            schema_url: URL or path to the schema
            
        Returns:
            Parsed schema with all references resolved
        """
        schema = self._load_schema(schema_url)
        return self._resolve_schema(schema, schema_url)
    
    def extract_message_structure(self, schema_url: str) -> Dict[str, Any]:
        """
        Extract the message structure from a schema.
        
        Returns a dict with:
        - required_fields: List of required field names
        - field_types: Dict of field_name -> type info
        - array_fields: Dict of array field structures
        
        Args:
            schema_url: URL or path to the schema
        """
        schema = self.parse_schema(schema_url)
        
        structure = {
            "required_fields": [],
            "field_types": {},
            "array_fields": {}
        }
        
        # Extract from resolved schema
        self._extract_from_schema(schema, structure)
        
        return structure
    
    def _load_schema(self, schema_ref: str) -> Dict:
        """Load schema from URL or local file, using cache if available."""
        # Check cache first
        if schema_ref in self.cache:
            logger.debug(f"Using cached schema: {schema_ref}")
            return self.cache[schema_ref]
        
        parsed_url = urlparse(schema_ref)
        
        if parsed_url.scheme in ['http', 'https']:
            # Try local file first (for offline development)
            local_path = self._url_to_local_path(schema_ref)
            if os.path.exists(local_path):
                logger.debug(f"Loading schema from local file: {local_path}")
                with open(local_path, 'r') as f:
                    schema = json.load(f)
            else:
                # Fetch from URL
                logger.debug(f"Fetching schema from URL: {schema_ref}")
                try:
                    response = requests.get(schema_ref, timeout=5)
                    response.raise_for_status()
                    schema = response.json()
                except Exception as e:
                    logger.error(f"Failed to fetch schema from {schema_ref}: {e}")
                    raise
        else:
            # Local file reference
            if not os.path.isabs(schema_ref):
                schema_ref = os.path.join(self.local_schema_dir, schema_ref)
            
            logger.debug(f"Loading schema from local file: {schema_ref}")
            with open(schema_ref, 'r') as f:
                schema = json.load(f)
        
        # Cache it
        self.cache[schema_ref] = schema
        return schema
    
    def _url_to_local_path(self, url: str) -> str:
        """Convert a GitHub Pages URL to local file path."""
        # https://aausmartproductionlab.github.io/AP2030-UNS/MQTTSchemas/moveToPosition.schema.json
        # -> MQTTSchemas/moveToPosition.schema.json
        if "github.io" in url and "/MQTTSchemas/" in url:
            filename = url.split("/MQTTSchemas/")[-1]
            return os.path.join(self.local_schema_dir, filename)
        return ""
    
    def _resolve_schema(self, schema: Dict, base_url: str) -> Dict:
        """Resolve all $ref and merge allOf, anyOf, oneOf."""
        resolved = {}
        
        # Handle $ref
        if "$ref" in schema:
            ref_url = schema["$ref"]
            ref_schema = self._resolve_reference(ref_url, base_url)
            resolved.update(ref_schema)
        
        # Handle allOf - merge all schemas
        if "allOf" in schema:
            for sub_schema in schema["allOf"]:
                resolved_sub = self._resolve_schema(sub_schema, base_url)
                resolved = self._merge_schemas(resolved, resolved_sub)
        
        # Handle anyOf / oneOf - just take first for now (could be smarter)
        if "anyOf" in schema:
            resolved_sub = self._resolve_schema(schema["anyOf"][0], base_url)
            resolved = self._merge_schemas(resolved, resolved_sub)
        
        if "oneOf" in schema:
            resolved_sub = self._resolve_schema(schema["oneOf"][0], base_url)
            resolved = self._merge_schemas(resolved, resolved_sub)
        
        # Merge other properties
        for key, value in schema.items():
            if key not in ["$ref", "allOf", "anyOf", "oneOf", "$schema"]:
                if key == "properties" and key in resolved:
                    # Merge properties
                    resolved[key].update(value)
                elif key == "required" and key in resolved:
                    # Merge required lists
                    resolved[key] = list(set(resolved[key] + value))
                else:
                    resolved[key] = value
        
        return resolved
    
    def _resolve_reference(self, ref: str, base_url: str) -> Dict:
        """Resolve a $ref to another schema."""
        if ref.startswith("#"):
            # Internal reference - not implemented yet
            logger.warning(f"Internal references not yet supported: {ref}")
            return {}
        
        # External reference
        if ref.startswith("http"):
            ref_url = ref
        else:
            # Relative reference - resolve against base
            parsed_base = urlparse(base_url)
            if parsed_base.scheme:
                # URL base
                base_path = "/".join(base_url.split("/")[:-1])
                ref_url = f"{base_path}/{ref}"
            else:
                # File base
                base_dir = os.path.dirname(base_url)
                ref_url = os.path.join(base_dir, ref)
        
        ref_schema = self._load_schema(ref_url)
        return self._resolve_schema(ref_schema, ref_url)
    
    def _merge_schemas(self, schema1: Dict, schema2: Dict) -> Dict:
        """Deep merge two schemas."""
        result = schema1.copy()
        
        for key, value in schema2.items():
            if key in result:
                if key == "properties":
                    result[key] = {**result[key], **value}
                elif key == "required":
                    result[key] = list(set(result[key] + value))
                elif isinstance(value, dict) and isinstance(result[key], dict):
                    result[key] = self._merge_schemas(result[key], value)
                else:
                    result[key] = value
            else:
                result[key] = value
        
        return result
    
    def _extract_from_schema(self, schema: Dict, structure: Dict):
        """Extract structure information from a resolved schema."""
        # Get required fields
        if "required" in schema:
            structure["required_fields"].extend(schema["required"])
        
        # Get properties
        if "properties" in schema:
            for prop_name, prop_def in schema["properties"].items():
                # Store field type info including format
                structure["field_types"][prop_name] = {
                    "type": prop_def.get("type"),
                    "format": prop_def.get("format"),  # e.g., "date-time" -> xs:dateTime
                    "description": prop_def.get("description")
                }
                
                # Check for arrays with prefixItems (Position array pattern)
                if prop_def.get("type") == "array" and "prefixItems" in prop_def:
                    structure["array_fields"][prop_name] = {
                        "items": []
                    }
                    for idx, item_def in enumerate(prop_def["prefixItems"]):
                        structure["array_fields"][prop_name]["items"].append({
                            "index": idx,
                            "title": item_def.get("title", f"item{idx}"),
                            "type": item_def.get("type"),
                            "description": item_def.get("description")
                        })
                    
                    # Check min/max items to determine optional fields
                    min_items = prop_def.get("minItems", len(prop_def["prefixItems"]))
                    max_items = prop_def.get("maxItems", len(prop_def["prefixItems"]))
                    structure["array_fields"][prop_name]["min_items"] = min_items
                    structure["array_fields"][prop_name]["max_items"] = max_items


def determine_field_mappings(
    aas_fields: List[str],
    schema_structure: Dict[str, Any]
) -> Tuple[Dict[str, List[Dict]], Dict[str, str], List[str]]:
    """
    Determine how AAS fields should map to MQTT message based on schema.
    
    Args:
        aas_fields: List of field names from AAS input variables
        schema_structure: Structure extracted from schema
        
    Returns:
        Tuple of (array_mappings, simple_mappings, unmapped_fields)
        - array_mappings: Dict of array_name -> list of field mappings
        - simple_mappings: Dict of schema_field -> {aas_field, type, format}
        - unmapped_fields: List of AAS fields that don't map to schema
    """
    array_mappings = {}
    simple_mappings = {}
    mapped_fields = set()
    
    # First, map simple (non-array) schema fields
    for field_name, field_info in schema_structure.get("field_types", {}).items():
        # Skip array fields (handled separately)
        if field_name in schema_structure.get("array_fields", {}):
            continue
        
        # Try to find matching AAS field (exact or case-insensitive)
        for aas_field in aas_fields:
            if aas_field == field_name or aas_field.lower() == field_name.lower():
                simple_mappings[field_name] = {
                    "aas_field": aas_field,
                    "type": field_info.get("type"),
                    "format": field_info.get("format")  # e.g., "date-time"
                }
                mapped_fields.add(aas_field)
                break
    
    # Check each array field in schema
    for array_name, array_info in schema_structure.get("array_fields", {}).items():
        mappings = []
        min_items = array_info.get("min_items", len(array_info["items"]))
        
        for item_info in array_info["items"]:
            title = item_info["title"]
            index = item_info["index"]
            
            # Try to find matching AAS field
            # Try exact match first, then case-insensitive
            matching_field = None
            for aas_field in aas_fields:
                if aas_field == title or aas_field.lower() == title.lower():
                    matching_field = aas_field
                    break
            
            if matching_field:
                mappings.append({
                    "aas_field": matching_field,
                    "json_field": title,
                    "index": index,
                    "optional": index >= min_items,
                    "default": 0.0 if item_info.get("type") == "number" else None
                })
                mapped_fields.add(matching_field)
            elif index < min_items:
                # Required field not found
                logger.warning(
                    f"Required array field '{title}' (index {index}) not found in AAS inputs"
                )
        
        if mappings:
            array_mappings[array_name] = mappings
    
    # Find unmapped fields
    unmapped_fields = [f for f in aas_fields if f not in mapped_fields]
    
    return array_mappings, simple_mappings, unmapped_fields
