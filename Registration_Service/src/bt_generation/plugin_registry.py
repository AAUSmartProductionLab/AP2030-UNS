"""
Schema-based Plugin Registry for BT Node Generation.

Instead of generating nodes per-asset, we generate per-schema since:
- Many assets share the same action schemas (e.g., command.schema.json)
- The Asset port already parameterizes which asset to talk to at runtime
- This creates a reusable plugin library

The registry tracks:
- Which schemas have been seen
- Which plugins exist for each schema
- Mapping from (schema_url) → plugin_class_name
"""

import json
import hashlib
import logging
from pathlib import Path
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field, asdict
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class SchemaPluginEntry:
    """Entry for a schema-based plugin."""
    schema_url: str
    schema_hash: str  # SHA256 of resolved schema for change detection
    class_name: str
    xml_tag: str
    generated_at: str
    assets_using: List[str] = field(default_factory=list)

    def add_asset(self, asset_id: str):
        if asset_id not in self.assets_using:
            self.assets_using.append(asset_id)


@dataclass
class ActionPluginEntry:
    """Entry for an action that maps to a schema plugin."""
    action_name: str
    input_schema_url: str
    output_schema_url: Optional[str]
    plugin_class: str  # Reference to SchemaPluginEntry.class_name
    has_response: bool
    is_synchronous: bool


class PluginRegistry:
    """
    Registry for schema-based BT plugins.

    Maintains a mapping of schemas → plugins so we can:
    1. Check if a plugin already exists when an asset registers
    2. Avoid generating duplicate code for identical schemas
    3. Track which assets use which plugins
    """

    REGISTRY_FILENAME = "plugin_registry.json"

    def __init__(self, registry_dir: str = "plugin_library"):
        """
        Initialize the registry.

        Args:
            registry_dir: Directory containing the plugin library and registry
        """
        self.registry_dir = Path(registry_dir)
        self.registry_file = self.registry_dir / self.REGISTRY_FILENAME

        # Schema URL → SchemaPluginEntry
        self.schema_plugins: Dict[str, SchemaPluginEntry] = {}

        # (asset_id, action_name) → ActionPluginEntry
        self.action_mappings: Dict[tuple, ActionPluginEntry] = {}

        # Load existing registry
        self._load()

    def _load(self):
        """Load registry from disk."""
        if self.registry_file.exists():
            try:
                data = json.loads(self.registry_file.read_text())

                for entry_data in data.get("schema_plugins", []):
                    entry = SchemaPluginEntry(**entry_data)
                    self.schema_plugins[entry.schema_url] = entry

                for key_str, entry_data in data.get("action_mappings", {}).items():
                    # Key is "asset_id|action_name"
                    parts = key_str.split("|", 1)
                    if len(parts) == 2:
                        key = tuple(parts)
                        self.action_mappings[key] = ActionPluginEntry(
                            **entry_data)

                logger.info(
                    f"Loaded registry with {len(self.schema_plugins)} schema plugins")
            except Exception as e:
                logger.warning(f"Failed to load registry: {e}")

    def save(self):
        """Save registry to disk."""
        self.registry_dir.mkdir(parents=True, exist_ok=True)

        data = {
            "version": "1.0",
            "updated_at": datetime.now().isoformat(),
            "schema_plugins": [asdict(e) for e in self.schema_plugins.values()],
            "action_mappings": {
                f"{k[0]}|{k[1]}": asdict(v)
                for k, v in self.action_mappings.items()
            }
        }

        self.registry_file.write_text(json.dumps(data, indent=2))
        logger.info(f"Saved registry to {self.registry_file}")

    def has_plugin_for_schema(self, schema_url: str) -> bool:
        """Check if we already have a plugin for this schema."""
        return schema_url in self.schema_plugins

    def get_plugin_for_schema(self, schema_url: str) -> Optional[SchemaPluginEntry]:
        """Get the plugin entry for a schema."""
        return self.schema_plugins.get(schema_url)

    def get_plugin_for_action(
        self,
        asset_id: str,
        action_name: str
    ) -> Optional[ActionPluginEntry]:
        """Get the plugin mapping for an asset's action."""
        return self.action_mappings.get((asset_id, action_name))

    def register_schema_plugin(
        self,
        schema_url: str,
        schema_hash: str,
        class_name: str,
        xml_tag: str
    ) -> SchemaPluginEntry:
        """Register a new schema-based plugin."""
        entry = SchemaPluginEntry(
            schema_url=schema_url,
            schema_hash=schema_hash,
            class_name=class_name,
            xml_tag=xml_tag,
            generated_at=datetime.now().isoformat(),
        )
        self.schema_plugins[schema_url] = entry
        logger.info(
            f"Registered new schema plugin: {class_name} for {schema_url}")
        return entry

    def register_action_mapping(
        self,
        asset_id: str,
        action_name: str,
        input_schema_url: str,
        output_schema_url: Optional[str],
        plugin_class: str,
        has_response: bool,
        is_synchronous: bool
    ):
        """Register an action → plugin mapping for an asset."""
        entry = ActionPluginEntry(
            action_name=action_name,
            input_schema_url=input_schema_url,
            output_schema_url=output_schema_url,
            plugin_class=plugin_class,
            has_response=has_response,
            is_synchronous=is_synchronous
        )
        self.action_mappings[(asset_id, action_name)] = entry

        # Also track which assets use this schema plugin
        if input_schema_url in self.schema_plugins:
            self.schema_plugins[input_schema_url].add_asset(asset_id)

    def get_missing_plugins(
        self,
        actions: List[Dict]
    ) -> tuple[List[Dict], List[Dict]]:
        """
        Check which actions need new plugins vs which already have plugins.

        Args:
            actions: List of action dicts from ConfigParser.get_actions()

        Returns:
            Tuple of (needs_generation, already_exists)
        """
        needs_generation = []
        already_exists = []

        for action in actions:
            schema_url = action.get('input_schema')
            if not schema_url:
                # Actions without schemas can use GenericActionNode
                already_exists.append(action)
                continue

            if self.has_plugin_for_schema(schema_url):
                already_exists.append(action)
            else:
                needs_generation.append(action)

        return needs_generation, already_exists

    def get_all_plugins(self) -> List[SchemaPluginEntry]:
        """Get all registered schema plugins."""
        return list(self.schema_plugins.values())

    def schema_to_class_name(self, schema_url: str) -> str:
        """
        Generate a consistent class name from a schema URL.

        Examples:
            moveToPosition.schema.json → MoveToPositionAction
            command.schema.json → CommandAction
            dispensingCommand.schema.json → DispensingCommandAction
        """
        # Extract filename from URL
        filename = schema_url.split("/")[-1]
        # Remove .schema.json or .json
        name = filename.replace(".schema.json", "").replace(".json", "")
        # Convert to PascalCase
        parts = name.replace("-", "_").replace(".", "_").split("_")
        pascal = "".join(p.capitalize() for p in parts)
        return f"{pascal}Action"

    def schema_to_xml_tag(self, schema_url: str) -> str:
        """
        Generate a consistent XML tag from a schema URL.

        Examples:
            moveToPosition.schema.json → moveToPosition
            command.schema.json → command
        """
        filename = schema_url.split("/")[-1]
        name = filename.replace(".schema.json", "").replace(".json", "")
        # camelCase
        parts = name.replace("-", "_").replace(".", "_").split("_")
        if not parts:
            return name
        return parts[0].lower() + "".join(p.capitalize() for p in parts[1:])


def compute_schema_hash(resolved_schema: Dict) -> str:
    """Compute a hash of the resolved schema for change detection."""
    # Sort keys for consistent hashing
    schema_str = json.dumps(resolved_schema, sort_keys=True)
    return hashlib.sha256(schema_str.encode()).hexdigest()[:16]
