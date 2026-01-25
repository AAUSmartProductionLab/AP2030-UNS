#!/usr/bin/env python3
"""
CLI tool for managing the schema-based BT plugin library.

This tool checks asset registrations against the existing plugin library
and generates new plugins only for schemas that don't have plugins yet.

Usage:
    # Check what plugins an asset needs
    python manage_bt_library.py check planarShuttle1.yaml
    
    # Generate missing plugins and update library
    python manage_bt_library.py generate planarShuttle1.yaml planarShuttle2.yaml
    
    # Show current library status
    python manage_bt_library.py status
    
    # Regenerate entire library (e.g., after template changes)
    python manage_bt_library.py rebuild
"""

from src.bt_generation import SchemaBasedGenerator, PluginRegistry
import argparse
import logging
import sys
import json
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).parent.parent))


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def cmd_check(args):
    """Check what plugins an asset needs."""
    generator = SchemaBasedGenerator(
        library_dir=args.library_dir,
        schema_base_dir=args.schema_dir
    )

    for config_path in args.configs:
        print(f"\n{'='*60}")
        print(f"Checking: {config_path}")
        print('='*60)

        try:
            needs_gen, existing, asset_id = generator.check_asset_registration(
                config_path)

            print(f"\nAsset: {asset_id}")

            if existing:
                print(f"\n✓ Actions with existing plugins ({len(existing)}):")
                for action in existing:
                    schema = action.get('input_schema', 'N/A')
                    plugin = generator.registry.get_plugin_for_schema(schema)
                    class_name = plugin.class_name if plugin else "GenericAction"
                    print(f"  - {action['name']} → {class_name}")

            if needs_gen:
                print(f"\n⚠ Actions needing new plugins ({len(needs_gen)}):")
                for action in needs_gen:
                    schema = action.get('input_schema', 'N/A')
                    class_name = generator.registry.schema_to_class_name(
                        schema)
                    print(f"  - {action['name']} → {class_name} (NEW)")
                    print(f"    Schema: {schema}")

            if not needs_gen:
                print(f"\n✓ All actions have existing plugins!")

        except Exception as e:
            print(f"Error: {e}")
            if args.verbose:
                import traceback
                traceback.print_exc()


def cmd_generate(args):
    """Generate missing plugins for assets."""
    generator = SchemaBasedGenerator(
        library_dir=args.library_dir,
        schema_base_dir=args.schema_dir
    )

    total_new = 0

    for config_path in args.configs:
        try:
            needs_gen, existing, asset_id = generator.check_asset_registration(
                config_path)

            if needs_gen:
                new_specs = generator.generate_for_actions(needs_gen, asset_id)
                total_new += len(new_specs)
                logger.info(
                    f"{asset_id}: Generated {len(new_specs)} new plugin spec(s)")
            else:
                logger.info(f"{asset_id}: No new plugins needed")

        except Exception as e:
            logger.error(f"Error processing {config_path}: {e}")
            if args.verbose:
                import traceback
                traceback.print_exc()

    if total_new > 0 or args.force:
        logger.info(f"Writing library with {total_new} new plugins...")
        try:
            lib_path = generator.write_library(library_name=args.library_name)
            print(f"\n{'='*60}")
            print(f"Library updated: {lib_path}")
            print(f"New plugins: {total_new}")
            print('='*60)

            # Print integration instructions
            print(f"""
To use in your BT Controller:

1. Copy {lib_path} to BT_Controller/

2. In CMakeLists.txt:
   add_subdirectory({args.library_name})
   target_link_libraries(bt_controller PRIVATE {args.library_name})

3. In your code:
   #include "{args.library_name}.hpp"
   
   // In registration:
   {args.library_name}::registerAllActions(
       factory, distributor, mqtt_client, aas_client);
""")
        except Exception as e:
            logger.error(f"Failed to write library: {e}")
            if args.verbose:
                import traceback
                traceback.print_exc()
    else:
        print("\nNo new plugins to generate.")


def cmd_status(args):
    """Show current library status."""
    registry = PluginRegistry(args.library_dir)

    print(f"\n{'='*60}")
    print(f"Plugin Library: {args.library_dir}")
    print('='*60)

    plugins = registry.get_all_plugins()

    if not plugins:
        print("\nNo plugins registered yet.")
        return

    print(f"\nRegistered Plugins: {len(plugins)}")
    print("-" * 60)

    for plugin in plugins:
        print(f"\n  {plugin.class_name} ({plugin.xml_tag})")
        print(f"    Schema: {plugin.schema_url.split('/')[-1]}")
        print(f"    Hash: {plugin.schema_hash}")
        if plugin.assets_using:
            print(f"    Used by: {', '.join(plugin.assets_using)}")

    # Show as JSON if requested
    if args.json:
        print("\n" + "=" * 60)
        print("JSON Registry:")
        print(json.dumps({
            "plugins": [
                {
                    "class": p.class_name,
                    "xml_tag": p.xml_tag,
                    "schema": p.schema_url,
                    "assets": p.assets_using
                }
                for p in plugins
            ]
        }, indent=2))


def cmd_rebuild(args):
    """Rebuild entire library from registry."""
    generator = SchemaBasedGenerator(
        library_dir=args.library_dir,
        schema_base_dir=args.schema_dir
    )

    try:
        library = generator.generate_library(
            library_name=args.library_name,
            include_existing=True
        )
        lib_path = generator.write_library(library)

        print(f"\n{'='*60}")
        print(f"Library rebuilt: {lib_path}")
        print(f"Total plugins: {len(library.nodes)}")
        print('='*60)

    except Exception as e:
        logger.error(f"Failed to rebuild library: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()


def main():
    parser = argparse.ArgumentParser(
        description='Manage the schema-based BT plugin library'
    )
    parser.add_argument(
        '-l', '--library-dir',
        default='plugin_library',
        help='Directory for the plugin library (default: plugin_library)'
    )
    parser.add_argument(
        '-s', '--schema-dir',
        default=None,
        help='Directory containing local JSON schema files'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose output'
    )

    subparsers = parser.add_subparsers(dest='command', required=True)

    # Check command
    check_parser = subparsers.add_parser(
        'check',
        help='Check what plugins an asset needs'
    )
    check_parser.add_argument('configs', nargs='+', help='YAML config files')
    check_parser.set_defaults(func=cmd_check)

    # Generate command
    gen_parser = subparsers.add_parser(
        'generate',
        help='Generate missing plugins for assets'
    )
    gen_parser.add_argument('configs', nargs='+', help='YAML config files')
    gen_parser.add_argument(
        '-n', '--library-name',
        default='aas_action_library',
        help='Name for the library'
    )
    gen_parser.add_argument(
        '-f', '--force',
        action='store_true',
        help='Write library even if no new plugins'
    )
    gen_parser.set_defaults(func=cmd_generate)

    # Status command
    status_parser = subparsers.add_parser(
        'status',
        help='Show current library status'
    )
    status_parser.add_argument(
        '--json',
        action='store_true',
        help='Output registry as JSON'
    )
    status_parser.set_defaults(func=cmd_status)

    # Rebuild command
    rebuild_parser = subparsers.add_parser(
        'rebuild',
        help='Rebuild entire library from registry'
    )
    rebuild_parser.add_argument(
        '-n', '--library-name',
        default='aas_action_library',
        help='Name for the library'
    )
    rebuild_parser.set_defaults(func=cmd_rebuild)

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    args.func(args)


if __name__ == '__main__':
    main()
