"""
Schema-Centric BehaviorTree.CPP Node Generator.

Generates ONE plugin class per unique input schema, not per asset.
This creates a reusable plugin library where:
- MoveToPositionAction works for ANY asset using moveToPosition.schema.json
- CommandAction works for ANY asset using command.schema.json
- The Asset port determines which asset to talk to at runtime

Benefits:
- Smaller plugin library
- No code duplication
- Pre-compile once, use for all assets
- Easy to track what plugins exist
"""

import os
import logging
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass, field
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from .cpp_type_mapper import CppTypeMapper, CppPortInfo
from .plugin_registry import PluginRegistry, compute_schema_hash, SchemaPluginEntry
from ..schema_parser import SchemaParser

logger = logging.getLogger(__name__)


@dataclass
class SchemaNodeSpec:
    """Specification for a schema-based action node."""
    # Identity (derived from schema, not asset)
    schema_url: str
    schema_hash: str
    class_name: str
    xml_tag: str

    # Ports derived from schema
    input_ports: List[CppPortInfo] = field(default_factory=list)

    # Array fields that need special message construction
    array_fields: Dict[str, List[CppPortInfo]] = field(default_factory=dict)

    # Tracking
    assets_using: List[str] = field(default_factory=list)


@dataclass
class GeneratedLibrary:
    """A complete generated plugin library."""
    library_name: str
    header_content: str
    source_content: str
    manifest_content: str
    cmake_content: str
    nodes: List[SchemaNodeSpec]
    registry_updated: bool


class SchemaBasedGenerator:
    """
    Generates a library of BT plugins based on unique schemas.

    Usage:
        generator = SchemaBasedGenerator(library_dir="plugin_library")

        # Check what's needed for an asset
        needed, existing = generator.check_asset_actions(config_path)

        # Generate only what's missing
        if needed:
            generator.generate_missing(needed)
            generator.write_library()
    """

    def __init__(
        self,
        library_dir: str = "plugin_library",
        template_dir: Optional[str] = None,
        schema_base_dir: Optional[str] = None
    ):
        """
        Initialize the generator.

        Args:
            library_dir: Directory for the plugin library
            template_dir: Directory containing Jinja2 templates
            schema_base_dir: Base directory for local JSON schema files
        """
        self.library_dir = Path(library_dir)
        self.template_dir = Path(template_dir or os.path.join(
            os.path.dirname(__file__), "templates"
        ))

        self.schema_parser = SchemaParser(local_schema_dir=schema_base_dir)
        self.type_mapper = CppTypeMapper()
        self.registry = PluginRegistry(str(self.library_dir))

        # Jinja2 environment
        self.jinja_env = Environment(
            loader=FileSystemLoader(str(self.template_dir)),
            trim_blocks=True,
            lstrip_blocks=True,
        )

        # Specs for schemas that need generation
        self.pending_specs: Dict[str, SchemaNodeSpec] = {}

    def check_asset_registration(
        self,
        config_path: str
    ) -> tuple[List[Dict], List[Dict], str]:
        """
        Check an asset registration to see what plugins are needed.

        Args:
            config_path: Path to asset YAML config

        Returns:
            Tuple of (needs_generation, already_exists, asset_id)
        """
        from ..config_parser import ConfigParser

        parser = ConfigParser(config_path=config_path)
        asset_id = parser.id_short
        actions = parser.get_actions()

        needs_generation, already_exists = self.registry.get_missing_plugins(
            actions)

        # Register action mappings for existing plugins
        for action in already_exists:
            schema_url = action.get('input_schema')
            if schema_url and self.registry.has_plugin_for_schema(schema_url):
                plugin = self.registry.get_plugin_for_schema(schema_url)
                self.registry.register_action_mapping(
                    asset_id=asset_id,
                    action_name=action['name'],
                    input_schema_url=schema_url,
                    output_schema_url=action.get('output_schema'),
                    plugin_class=plugin.class_name,
                    has_response=action.get('has_response', True),
                    is_synchronous=action.get('synchronous', True)
                )

        logger.info(
            f"Asset {asset_id}: {len(already_exists)} actions have plugins, "
            f"{len(needs_generation)} need generation"
        )

        return needs_generation, already_exists, asset_id

    def generate_for_actions(
        self,
        actions: List[Dict],
        asset_id: str
    ) -> List[SchemaNodeSpec]:
        """
        Generate specs for actions that need new plugins.

        Args:
            actions: Actions that need plugin generation
            asset_id: Asset ID for tracking

        Returns:
            List of new SchemaNodeSpec created
        """
        new_specs = []

        for action in actions:
            schema_url = action.get('input_schema')
            if not schema_url:
                continue

            # Skip if already pending or registered
            if schema_url in self.pending_specs:
                self.pending_specs[schema_url].assets_using.append(asset_id)
                continue

            if self.registry.has_plugin_for_schema(schema_url):
                continue

            try:
                spec = self._create_schema_spec(schema_url, asset_id)
                if spec:
                    self.pending_specs[schema_url] = spec
                    new_specs.append(spec)

                    # Register the action mapping
                    self.registry.register_action_mapping(
                        asset_id=asset_id,
                        action_name=action['name'],
                        input_schema_url=schema_url,
                        output_schema_url=action.get('output_schema'),
                        plugin_class=spec.class_name,
                        has_response=action.get('has_response', True),
                        is_synchronous=action.get('synchronous', True)
                    )
            except Exception as e:
                logger.error(
                    f"Failed to generate spec for schema {schema_url}: {e}")

        return new_specs

    def _create_schema_spec(
        self,
        schema_url: str,
        asset_id: str
    ) -> Optional[SchemaNodeSpec]:
        """Create a node specification from a schema URL."""

        # Parse and resolve the schema
        resolved_schema = self.schema_parser.parse_schema(schema_url)
        schema_hash = compute_schema_hash(resolved_schema)

        # Generate class name and XML tag from schema URL
        class_name = self.registry.schema_to_class_name(schema_url)
        xml_tag = self.registry.schema_to_xml_tag(schema_url)

        spec = SchemaNodeSpec(
            schema_url=schema_url,
            schema_hash=schema_hash,
            class_name=class_name,
            xml_tag=xml_tag,
            assets_using=[asset_id],
        )

        # Extract ports from schema
        spec.input_ports = self.type_mapper.extract_ports_from_schema(
            resolved_schema)

        # Group array element ports
        for port in spec.input_ports:
            if port.is_array_element and port.array_name:
                if port.array_name not in spec.array_fields:
                    spec.array_fields[port.array_name] = []
                spec.array_fields[port.array_name].append(port)

        logger.info(f"Created spec: {class_name} for {schema_url}")
        return spec

    def generate_library(
        self,
        library_name: str = "aas_action_library",
        include_existing: bool = True
    ) -> GeneratedLibrary:
        """
        Generate the complete plugin library.

        Args:
            library_name: Name for the library
            include_existing: Whether to include already-registered plugins

        Returns:
            GeneratedLibrary with all content
        """
        # Collect all specs
        all_specs = list(self.pending_specs.values())

        if include_existing:
            # Regenerate from existing registry entries
            for entry in self.registry.get_all_plugins():
                if entry.schema_url not in self.pending_specs:
                    try:
                        spec = self._create_schema_spec(
                            entry.schema_url,
                            entry.assets_using[0] if entry.assets_using else "unknown"
                        )
                        if spec:
                            all_specs.append(spec)
                    except Exception as e:
                        logger.warning(
                            f"Could not regenerate {entry.class_name}: {e}")

        if not all_specs:
            raise ValueError("No specs to generate")

        # Register new plugins
        for spec in self.pending_specs.values():
            self.registry.register_schema_plugin(
                schema_url=spec.schema_url,
                schema_hash=spec.schema_hash,
                class_name=spec.class_name,
                xml_tag=spec.xml_tag
            )

        # Load and render templates
        header_template = self.jinja_env.get_template(
            "schema_action_node.hpp.jinja2")
        source_template = self.jinja_env.get_template(
            "schema_action_node.cpp.jinja2")
        manifest_template = self.jinja_env.get_template(
            "schema_plugin_manifest.xml.jinja2")
        cmake_template = self.jinja_env.get_template(
            "schema_library_cmake.jinja2")

        context = {
            "library_name": library_name,
            "nodes": all_specs,
            "type_mapper": self.type_mapper,
            "include_guard": library_name.upper().replace("-", "_").replace(".", "_"),
        }

        return GeneratedLibrary(
            library_name=library_name,
            header_content=header_template.render(**context),
            source_content=source_template.render(**context),
            manifest_content=manifest_template.render(**context),
            cmake_content=cmake_template.render(**context),
            nodes=all_specs,
            registry_updated=bool(self.pending_specs),
        )

    def write_library(
        self,
        library: Optional[GeneratedLibrary] = None,
        library_name: str = "aas_action_library"
    ) -> Path:
        """
        Write the library files to disk.

        Args:
            library: Pre-generated library, or generate new one
            library_name: Name if generating new

        Returns:
            Path to the library directory
        """
        if library is None:
            library = self.generate_library(library_name)

        # Create directory structure
        lib_path = self.library_dir / library.library_name
        include_path = lib_path / "include"
        src_path = lib_path / "src"

        lib_path.mkdir(parents=True, exist_ok=True)
        include_path.mkdir(exist_ok=True)
        src_path.mkdir(exist_ok=True)

        # Write files
        (include_path /
         f"{library.library_name}.hpp").write_text(library.header_content)
        (src_path /
         f"{library.library_name}.cpp").write_text(library.source_content)
        (lib_path /
         f"{library.library_name}_manifest.xml").write_text(library.manifest_content)
        (lib_path / "CMakeLists.txt").write_text(library.cmake_content)

        # Save registry
        self.registry.save()

        # Clear pending specs
        self.pending_specs.clear()

        logger.info(f"Wrote library to {lib_path}")
        return lib_path

    def get_plugin_status(self) -> Dict[str, Any]:
        """Get current status of the plugin library."""
        return {
            "registered_plugins": len(self.registry.schema_plugins),
            "pending_generation": len(self.pending_specs),
            "plugins": [
                {
                    "class": e.class_name,
                    "schema": e.schema_url,
                    "assets_using": e.assets_using
                }
                for e in self.registry.get_all_plugins()
            ]
        }
