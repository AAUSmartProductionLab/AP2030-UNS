#!/usr/bin/env python3
"""
Migrate legacy YAML AAS configs to new JSON format.

Reads legacy YAML files from AASDescriptions/Resource/configs/ (or a given
directory), normalizes them via AssetConfig, and writes the new-format JSON
next to each source file.

Usage::

    cd Registration_Service
    python scripts/migrate_configs.py                          # all Resource configs
    python scripts/migrate_configs.py --dir ../AASDescriptions/Resource/configs
    python scripts/migrate_configs.py --file path/to/config.yaml  # single file
    python scripts/migrate_configs.py --dry-run                   # preview only
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))
sys.path.insert(0, str(_HERE.parent / "third_party" / "aas_pydantic"))


def migrate_file(yaml_path: Path, dry_run: bool = False) -> bool:
    """Convert a single legacy YAML file to new-format JSON."""
    from src.config_parser import parse_config_file

    try:
        asset = parse_config_file(str(yaml_path))
        

        # Build the new-format dict from the validated Pydantic model
        new_data: dict = {
            "$schema": "https://smartproductionlab.aau.dk/schemas/resource_asset.json",
            "id": asset.id,
            "id_short": asset.id_short,
            "global_asset_id": asset.global_asset_id or asset.id,
            "asset_type": asset.asset_type,
            "serial_number": asset.serial_number,
            "location": asset.location,
            "derived_from": asset.derived_from,
            "asset_kind": asset.asset_kind,
        }

        # Serialize each non-None submodel
        for field_name in (
            "nameplate",
            "asset_interfaces_description",
            "control_component_instance",
            "capability_description",
            "hierarchical_structures",
            "variables",
            "parameters",
        ):
            sm = getattr(asset, field_name, None)
            if sm is not None:
                try:
                    new_data[field_name] = json.loads(
                        sm.model_dump_json(exclude_none=True)
                    )
                except Exception:
                    new_data[field_name] = sm.model_dump()

        json_path = yaml_path.with_suffix(".json")
        if dry_run:
            print(f"  [DRY RUN] Would write: {json_path}")
            return True

        with open(json_path, "w") as f:
            json.dump(new_data, f, indent=2)
        print(f"  ✅ Migrated: {yaml_path.name} → {json_path.name}")
        return True

    except Exception as e:
        print(f"  ❌ Failed {yaml_path.name}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Migrate legacy YAML AAS configs to new JSON format"
    )
    parser.add_argument(
        "--dir",
        default=str(Path(__file__).resolve().parent.parent.parent / "AASDescriptions" / "Resource" / "configs"),
        help="Directory containing YAML configs",
    )
    parser.add_argument("--file", help="Single YAML file to migrate")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, do not write files")
    args = parser.parse_args()

    if args.file:
        paths = [Path(args.file)]
    else:
        config_dir = Path(args.dir)
        if not config_dir.exists():
            print(f"❌ Directory not found: {config_dir}")
            sys.exit(1)
        paths = sorted(config_dir.glob("*.yaml")) + sorted(config_dir.glob("*.yml"))

    if not paths:
        print("No YAML files found.")
        sys.exit(1)

    print(f"Migrating {len(paths)} config(s)...")
    if args.dry_run:
        print("(DRY RUN — no files will be written)")

    succeeded = 0
    for p in paths:
        if migrate_file(p, args.dry_run):
            succeeded += 1

    print(f"\nDone: {succeeded}/{len(paths)} succeeded")


if __name__ == "__main__":
    main()
