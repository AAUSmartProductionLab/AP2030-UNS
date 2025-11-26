#!/usr/bin/env python3
"""
PlatformIO pre-build script to copy config.json from schemas directory
into the data/ folder for LittleFS filesystem upload.
"""
Import("env")  # pylint: disable=undefined-variable
import os
import shutil

# Get the project directory and build environment
project_dir = env.get("PROJECT_DIR")
build_env = env.get("PIOENV")

# Determine which config file to use based on the environment
config_files = {
    "filling": "imaFillingSystem.json",
    "filling_wrover": "imaFillingSystem.json",
    "stoppering": "syntegonStopperingSystem.json"
}

# Source config file path (relative to project root)
source_config = os.path.join(project_dir, "..", "..", "schemas", "ResourceDescription", 
                              config_files[build_env])
source_config = os.path.abspath(source_config)

# Target data directory
data_dir = os.path.join(project_dir, "data")
target_config = os.path.join(data_dir, "config.json")

# Create data directory if it doesn't exist
os.makedirs(data_dir, exist_ok=True)

# Copy the config file
if os.path.exists(source_config):
    shutil.copy2(source_config, target_config)
    print(f"✓ Copied config for '{build_env}': {config_files.get(build_env)} → config.json")
    file_size = os.path.getsize(target_config)
    print(f"  Config size: {file_size:,} bytes ({file_size/1024:.1f} KB)")
else:
    print(f"⚠ WARNING: Config file not found at {source_config}")
    print(f"  Expected: {config_files.get(build_env)} for environment '{build_env}'")
    print("  LittleFS will be uploaded without config.json")
