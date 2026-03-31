#!/usr/bin/env python3
"""
PlatformIO pre-build script to:
1. Copy YAML config from AASDescriptions/Resource/configs/ into the data/ folder for LittleFS
2. Read network configuration from root .env file and inject as build flags

The YAML config is a lightweight asset description that the Registration Service
will use to generate the full AAS description.
"""
import shutil
import os
Import("env")  # pylint: disable=undefined-variable


def load_env_file(env_path):
    """Load variables from a .env file."""
    env_vars = {}
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                # Skip comments and empty lines
                if not line or line.startswith('#'):
                    continue
                # Parse KEY=VALUE
                if '=' in line:
                    key, value = line.split('=', 1)
                    # Remove quotes if present
                    value = value.strip().strip('"').strip("'")
                    env_vars[key.strip()] = value
    return env_vars


# Get the project directory and build environment
project_dir = env.get("PROJECT_DIR")
build_env = env.get("PIOENV")

# =============================================================================
# PART 1: Load network config from root .env file
# =============================================================================
root_env_file = os.path.join(project_dir, "..", "..", ".env")
root_env_file = os.path.abspath(root_env_file)

env_vars = load_env_file(root_env_file)

# Get MQTT configuration from .env (with defaults)
mqtt_broker = env_vars.get("EXTERNAL_HOST", "192.168.0.104")
mqtt_port = env_vars.get("MQTT_PORT", "1883")

# Get WiFi configuration from .env (with defaults)
wifi_ssid = env_vars.get("WIFI_SSID", "AP2030")
wifi_password = env_vars.get("WIFI_PASSWORD", "NovoNordisk")

# Inject as build flags so they're available at compile time
env.Append(CPPDEFINES=[
    ("MQTT_SERVER", f'\\"{mqtt_broker}\\"'),
    ("MQTT_PORT_NUM", mqtt_port),
    ("WIFI_SSID_ENV", f'\\"{wifi_ssid}\\"'),
    ("WIFI_PASSWORD_ENV", f'\\"{wifi_password}\\"'),
])

if os.path.exists(root_env_file):
    print(f"✓ Loaded network config from .env:")
    print(f"  MQTT_SERVER = {mqtt_broker}")
    print(f"  MQTT_PORT = {mqtt_port}")
    print(f"  WIFI_SSID = {wifi_ssid}")
    print(f"  WIFI_PASSWORD = {'*' * len(wifi_password)}")
else:
    print(f"⚠ No .env file found at {root_env_file}, using defaults")
    print(f"  MQTT_SERVER = {mqtt_broker} (default)")
    print(f"  MQTT_PORT = {mqtt_port} (default)")
    print(f"  WIFI_SSID = {wifi_ssid} (default)")

# =============================================================================
# PART 2: Copy YAML config for LittleFS
# =============================================================================

# Determine which YAML config file to use based on the environment
# These files are located in AASDescriptions/Resource/configs/
config_files = {
    "filling": "imaDispensing.yaml",
    "filling_wrover": "aauFillingLine.yaml",
    "stoppering": "syntegonStoppering.yaml",
    "dispensing": "imaDispensing.yaml"
}

# Source config file path (from AASDescriptions/Resource/configs/)
source_config = os.path.join(project_dir, "..", "..", "AASDescriptions", "Resource", "configs",
                             config_files[build_env])
source_config = os.path.abspath(source_config)

# Target data directory
data_dir = os.path.join(project_dir, "data")
target_config = os.path.join(data_dir, "config.yaml")

# Create data directory if it doesn't exist
os.makedirs(data_dir, exist_ok=True)

# Copy the config file with retry logic for OneDrive sync issues
if os.path.exists(source_config):
    import time
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # Remove existing file first if it exists
            if os.path.exists(target_config):
                try:
                    os.remove(target_config)
                except (PermissionError, FileNotFoundError):
                    # File is locked or disappeared (OneDrive sync issue)
                    if attempt < max_retries - 1:
                        print(
                            f"  File locked or syncing, waiting... (attempt {attempt + 1}/{max_retries})")
                        time.sleep(0.5)
                        continue
                    elif isinstance(e, PermissionError):
                        raise

            # Copy the file
            shutil.copy2(source_config, target_config)
            print(
                f"✓ Copied YAML config for '{build_env}': {config_files.get(build_env)} → config.yaml")
            file_size = os.path.getsize(target_config)
            print(
                f"  Config size: {file_size:,} bytes ({file_size/1024:.1f} KB)")
            break  # Success, exit retry loop

        except PermissionError as e:
            if attempt < max_retries - 1:
                print(
                    f"  Permission error, retrying... (attempt {attempt + 1}/{max_retries})")
                time.sleep(0.5)
            else:
                print(
                    f"✗ ERROR: Could not copy config file after {max_retries} attempts")
                print(f"  Error: {e}")
                print(
                    "  Tip: Close any programs that might have the file open (OneDrive, editors, etc.)")
                raise
else:
    print(f"⚠ WARNING: YAML config file not found at {source_config}")
    print(
        f"  Expected: {config_files.get(build_env)} for environment '{build_env}'")
    print("  LittleFS will be uploaded without config.yaml")
