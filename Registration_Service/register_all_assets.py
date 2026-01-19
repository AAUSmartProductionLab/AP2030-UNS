#!/usr/bin/env python3
"""
Register All Assets via MQTT

Publishes all asset configuration files to MQTT so the registration service
can process them and register with BaSyx.

Usage:
    python register_all_assets.py
    python register_all_assets.py --config-dir ../AASDescriptions/Resource/configs
    python register_all_assets.py --mqtt-broker 192.168.0.104 --dry-run
"""

import sys
import os
import time
import json
from pathlib import Path
from typing import List, Dict, Tuple
import argparse

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

# Load environment variables from .env file BEFORE importing anything else
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent / '.env'
if env_path.exists():
    load_dotenv(env_path)

import yaml
import paho.mqtt.client as mqtt

# Now import after .env is loaded
from src.core.constants import (
    DEFAULT_MQTT_BROKER,
    DEFAULT_MQTT_PORT,
    PathDefaults
)


class Colors:
    """ANSI color codes for terminal output"""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    END = '\033[0m'


def print_header(text):
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*70}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text:^70}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*70}{Colors.END}\n")


def print_success(text):
    print(f"{Colors.GREEN}✓ {text}{Colors.END}")


def print_failure(text):
    print(f"{Colors.RED}✗ {text}{Colors.END}")


def print_warning(text):
    print(f"{Colors.YELLOW}⚠ {text}{Colors.END}")


def print_info(text):
    print(f"{Colors.CYAN}  → {text}{Colors.END}")


def print_progress(current, total, text):
    print(f"{Colors.MAGENTA}[{current}/{total}] {text}{Colors.END}")


def find_config_files(config_dir: str) -> List[Path]:
    """Find all YAML config files in the specified directory"""
    config_path = Path(config_dir)

    if not config_path.exists():
        print_failure(f"Config directory not found: {config_dir}")
        return []

    # Find all .yaml and .yml files
    yaml_files = list(config_path.glob("*.yaml")) + \
        list(config_path.glob("*.yml"))

    return sorted(yaml_files)


def get_asset_info(config_path: Path) -> Dict[str, str]:
    """Extract basic asset information from config file"""
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        # Config contains a single system with the system ID as the top-level key
        system_id = list(config.keys())[0]
        system_config = config[system_id]
        
        return {
            'system_id': system_id,
            'id_short': system_config.get('idShort', system_id),
            'aas_id': system_config.get('id', ''),
            'file_name': config_path.name
        }
    except Exception as e:
        return {
            'system_id': 'UNKNOWN',
            'id_short': 'UNKNOWN',
            'aas_id': 'UNKNOWN',
            'file_name': config_path.name,
            'error': str(e)
        }


def publish_config(
    config_path: Path,
    mqtt_client: mqtt.Client,
    base_topic: str = "NN/Nybrovej/InnoLab",
    delay: float = 0.5
) -> Tuple[bool, Dict]:
    """
    Publish a config file to MQTT for registration.

    Args:
        config_path: Path to the YAML config file
        mqtt_client: Connected MQTT client
        base_topic: Base MQTT topic prefix
        delay: Delay after publishing (seconds)

    Returns:
        Tuple of (success, result_info)
    """
    try:
        # Get asset info
        asset_info = get_asset_info(config_path)

        if 'error' in asset_info:
            print_failure(f"Failed to parse config: {asset_info['error']}")
            return False, {'error': 'Config parsing failed', **asset_info}

        system_id = asset_info['system_id']
        
        # Read the raw YAML content
        with open(config_path, 'r') as f:
            yaml_content = f.read()

        # Build the topic: NN/Nybrovej/InnoLab/{systemId}/Registration/Config
        topic = f"{base_topic}/{system_id}/Registration/Config"

        print_info(f"Publishing to: {topic}")
        print_info(f"  ID Short: {asset_info['id_short']}")

        # Publish the raw YAML content
        result = mqtt_client.publish(topic, yaml_content, qos=2)
        result.wait_for_publish()

        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            print_success(f"Published {asset_info['id_short']}")
            # Small delay to allow registration service to process
            time.sleep(delay)
            return True, {'published': True, **asset_info}
        else:
            print_failure(f"Failed to publish: {result.rc}")
            return False, {'published': False, 'error': f'MQTT error: {result.rc}', **asset_info}

    except Exception as e:
        print_failure(f"Error publishing {config_path.name}: {e}")
        import traceback
        traceback.print_exc()
        return False, {'error': str(e), 'file_name': config_path.name}


def check_mqtt_connection(broker: str, port: int) -> Tuple[bool, mqtt.Client]:
    """
    Connect to MQTT broker.
    
    Returns:
        Tuple of (success, client)
    """
    try:
        client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"asset-publisher-{os.getpid()}"
        )
        
        connected = False
        
        def on_connect(client, userdata, flags, reason_code, properties):
            nonlocal connected
            if reason_code == 0:
                connected = True
        
        client.on_connect = on_connect
        client.connect(broker, port, keepalive=60)
        client.loop_start()
        
        # Wait for connection
        for _ in range(50):  # 5 seconds timeout
            if connected:
                return True, client
            time.sleep(0.1)
        
        print_failure(f"Connection timeout to {broker}:{port}")
        return False, None
        
    except Exception as e:
        print_failure(f"Cannot connect to MQTT broker at {broker}:{port}: {e}")
        return False, None


def main():
    parser = argparse.ArgumentParser(
        description='Publish all asset configs to MQTT for registration',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Publish all assets with default settings
  python register_all_assets.py
  
  # Use custom config directory
  python register_all_assets.py --config-dir /path/to/configs
  
  # Dry run (no actual publishing)
  python register_all_assets.py --dry-run
  
  # Custom MQTT broker
  python register_all_assets.py --mqtt-broker 192.168.0.104
        """
    )

    parser.add_argument(
        '--config-dir',
        default=f'../{PathDefaults.CONFIG_DIR}',
        help=f'Directory containing config YAML files (default: ../{PathDefaults.CONFIG_DIR})'
    )
    parser.add_argument(
        '--mqtt-broker',
        default=DEFAULT_MQTT_BROKER,
        help=f'MQTT broker host (default: {DEFAULT_MQTT_BROKER})'
    )
    parser.add_argument(
        '--mqtt-port',
        type=int,
        default=DEFAULT_MQTT_PORT,
        help=f'MQTT broker port (default: {DEFAULT_MQTT_PORT})'
    )
    parser.add_argument(
        '--base-topic',
        default='NN/Nybrovej/InnoLab',
        help='Base MQTT topic prefix (default: NN/Nybrovej/InnoLab)'
    )
    parser.add_argument(
        '--delay',
        type=float,
        default=1.0,
        help='Delay between publishing each config in seconds (default: 1.0)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be published without actually publishing'
    )
    parser.add_argument(
        '--continue-on-error',
        action='store_true',
        default=True,
        help='Continue processing remaining configs if one fails (default: True)'
    )
    parser.add_argument(
        '--filter',
        help='Only process config files matching this pattern (e.g., "planar*")'
    )

    args = parser.parse_args()

    # Resolve config directory path
    script_dir = Path(__file__).parent
    config_dir = script_dir / args.config_dir

    print_header("Asset Registration via MQTT")
    print(f"{Colors.BOLD}Configuration:{Colors.END}")
    print(f"  Config Dir: {config_dir}")
    print(f"  MQTT Broker: {args.mqtt_broker}:{args.mqtt_port}")
    print(f"  Base Topic: {args.base_topic}")
    print(f"  Delay: {args.delay}s")
    print(f"  Dry Run: {args.dry_run}")
    if args.filter:
        print(f"  Filter: {args.filter}")
    print()

    # Find config files
    print_info("Scanning for configuration files...")
    config_files = find_config_files(str(config_dir))

    if not config_files:
        print_failure("No configuration files found!")
        return 1

    # Apply filter if specified
    if args.filter:
        from fnmatch import fnmatch
        config_files = [
            f for f in config_files if fnmatch(f.name, args.filter)]
        print_info(
            f"Filtered to {len(config_files)} files matching '{args.filter}'")

    print_success(f"Found {len(config_files)} configuration file(s)")
    for f in config_files:
        print_info(f"  - {f.name}")
    print()

    # Connect to MQTT (unless dry run)
    mqtt_client = None
    if not args.dry_run:
        print_info("Connecting to MQTT broker...")
        success, mqtt_client = check_mqtt_connection(args.mqtt_broker, args.mqtt_port)
        if not success:
            print_failure("Cannot connect to MQTT broker. Exiting.")
            return 1
        print_success("Connected to MQTT broker\n")

    # Process each config file
    print_header("Publishing Configs")

    results = {
        'total': len(config_files),
        'successful': [],
        'failed': [],
        'skipped': []
    }

    for idx, config_file in enumerate(config_files, 1):
        print_progress(idx, len(config_files), f"Processing {config_file.name}")

        if args.dry_run:
            # Just show what would be published
            asset_info = get_asset_info(config_file)
            if 'error' in asset_info:
                print_failure(f"Cannot parse config: {asset_info['error']}")
                results['failed'].append(asset_info)
            else:
                topic = f"{args.base_topic}/{asset_info['system_id']}/Registration/Config"
                print_info(f"Would publish to: {topic}")
                print_info(f"  ID Short: {asset_info['id_short']}")
                results['skipped'].append(asset_info)
        else:
            # Actual publishing
            success, result_info = publish_config(
                config_file,
                mqtt_client,
                base_topic=args.base_topic,
                delay=args.delay
            )

            if success:
                results['successful'].append(result_info)
            else:
                results['failed'].append(result_info)
                if not args.continue_on_error:
                    print_failure(
                        "Stopping due to error (use --continue-on-error to continue)")
                    break

        print()  # Spacing between assets

    # Cleanup MQTT connection
    if mqtt_client:
        mqtt_client.loop_stop()
        mqtt_client.disconnect()

    # Summary
    print_header("Publishing Summary")

    if args.dry_run:
        print(f"{Colors.BOLD}Dry Run - No configs were actually published{Colors.END}\n")
        print(f"Total configs found: {results['total']}")
        print(f"  Valid configs: {len(results['skipped'])}")
        print(f"  Invalid configs: {len(results['failed'])}")
    else:
        print(f"{Colors.BOLD}Total: {results['total']}{Colors.END}")
        print(f"{Colors.GREEN}Published: {len(results['successful'])}{Colors.END}")
        print(f"{Colors.RED}Failed: {len(results['failed'])}{Colors.END}")
        print()

        if results['successful']:
            print(f"{Colors.BOLD}Successfully Published:{Colors.END}")
            for asset in results['successful']:
                print_success(f"{asset['id_short']} ({asset['file_name']})")
            print()

        if results['failed']:
            print(f"{Colors.BOLD}Failed:{Colors.END}")
            for asset in results['failed']:
                file_name = asset.get('file_name', 'unknown')
                error = asset.get('error', 'Unknown error')
                print_failure(f"{file_name}: {error}")
            print()

        print_info("Check registration-service logs for registration results:")
        print_info("  docker compose logs registration-service --tail 100")

    # Return exit code
    if args.dry_run:
        return 0
    else:
        return 0 if len(results['failed']) == 0 else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Operation cancelled by user{Colors.END}")
        sys.exit(130)
    except Exception as e:
        print_failure(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
