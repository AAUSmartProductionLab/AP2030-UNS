#!/usr/bin/env python3
"""
Register All Assets Script

Registers all assets that have configuration files in the configs folder.
Processes each YAML config file and registers it with BaSyx.

Usage:
    python register_all_assets.py
    python register_all_assets.py --config-dir ../AASDescriptions/Resource/configs
    python register_all_assets.py --basyx-url http://localhost:8081 --dry-run
    python register_all_assets.py --validate --keep-output
"""

import sys
import os
import json
import tempfile
import shutil
from pathlib import Path
from typing import List, Dict, Tuple
import argparse

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src import (
    UnifiedRegistrationService,
    BaSyxConfig,
    ConfigParser
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
    yaml_files = list(config_path.glob("*.yaml")) + list(config_path.glob("*.yml"))
    
    return sorted(yaml_files)


def get_asset_info(config_path: Path) -> Dict[str, str]:
    """Extract basic asset information from config file"""
    try:
        parser = ConfigParser(config_path=str(config_path))
        return {
            'id_short': parser.id_short,
            'aas_id': parser.aas_id,
            'global_asset_id': parser.global_asset_id,
            'file_name': config_path.name
        }
    except Exception as e:
        return {
            'id_short': 'UNKNOWN',
            'aas_id': 'UNKNOWN',
            'global_asset_id': 'UNKNOWN',
            'file_name': config_path.name,
            'error': str(e)
        }


def register_asset(
    config_path: Path,
    service: UnifiedRegistrationService,
    validate: bool = True,
    output_dir: str = None
) -> Tuple[bool, Dict]:
    """
    Register a single asset from its config file
    
    Returns:
        Tuple of (success, result_info)
    """
    try:
        print_info(f"Processing {config_path.name}...")
        
        # Get asset info
        asset_info = get_asset_info(config_path)
        
        if 'error' in asset_info:
            print_failure(f"Failed to parse config: {asset_info['error']}")
            return False, {'error': 'Config parsing failed', **asset_info}
        
        print_info(f"  ID Short: {asset_info['id_short']}")
        print_info(f"  AAS ID: {asset_info['aas_id']}")
        
        # Register (without restarting services for each asset)
        success = service.register_from_yaml_config(
            config_path=str(config_path),
            validate_aas=validate,
            restart_services=False
        )
        
        if success:
            print_success(f"Successfully registered {asset_info['id_short']}")
            return True, {'registered': True, **asset_info}
        else:
            print_failure(f"Registration failed for {asset_info['id_short']}")
            return False, {'registered': False, 'error': 'Registration failed', **asset_info}
            
    except Exception as e:
        print_failure(f"Error registering {config_path.name}: {e}")
        import traceback
        traceback.print_exc()
        return False, {'error': str(e), 'file_name': config_path.name}


def check_basyx_connection(basyx_url: str) -> bool:
    """Check if BaSyx server is reachable"""
    import requests
    try:
        response = requests.get(f"{basyx_url}/shells", timeout=5)
        if response.status_code in [200, 401]:
            return True
        else:
            print_warning(f"BaSyx returned status {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print_failure(f"Cannot connect to BaSyx at {basyx_url}")
        return False
    except Exception as e:
        print_failure(f"Error checking BaSyx connection: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description='Register all assets from config files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Register all assets with default settings
  python register_all_assets.py
  
  # Use custom config directory
  python register_all_assets.py --config-dir /path/to/configs
  
  # Dry run (no actual registration)
  python register_all_assets.py --dry-run
  
  # Custom BaSyx URL with validation
  python register_all_assets.py --basyx-url http://192.168.0.104:8081 --validate
        """
    )
    
    parser.add_argument(
        '--config-dir',
        default='../AASDescriptions/Resource/configs',
        help='Directory containing config YAML files (default: ../AASDescriptions/Resource/configs)'
    )
    parser.add_argument(
        '--basyx-url',
        default='http://192.168.0.104:8081',
        help='BaSyx server URL (default: http://192.168.0.104:8081)'
    )
    parser.add_argument(
        '--mqtt-broker',
        default='192.168.0.104',
        help='MQTT broker host (default: 192.168.0.104)'
    )
    parser.add_argument(
        '--mqtt-port',
        type=int,
        default=1883,
        help='MQTT broker port (default: 1883)'
    )
    parser.add_argument(
        '--delegation-url',
        default='http://192.168.0.104:8087',
        help='Operation delegation service URL (default: http://192.168.0.104:8087)'
    )
    parser.add_argument(
        '--validate',
        action='store_true',
        help='Validate AAS before registration'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be registered without actually registering'
    )
    parser.add_argument(
        '--keep-output',
        action='store_true',
        help='Keep generated output files'
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
    
    print_header("Asset Registration Service")
    print(f"{Colors.BOLD}Configuration:{Colors.END}")
    print(f"  Config Dir: {config_dir}")
    print(f"  BaSyx URL: {args.basyx_url}")
    print(f"  MQTT Broker: {args.mqtt_broker}:{args.mqtt_port}")
    print(f"  Delegation Service: {args.delegation_url}")
    print(f"  Validate: {args.validate}")
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
        config_files = [f for f in config_files if fnmatch(f.name, args.filter)]
        print_info(f"Filtered to {len(config_files)} files matching '{args.filter}'")
    
    print_success(f"Found {len(config_files)} configuration file(s)")
    for f in config_files:
        print_info(f"  - {f.name}")
    print()
    
    # Create temp output directory if keeping output
    output_dir = None
    if args.keep_output:
        output_dir = tempfile.mkdtemp(prefix='asset_registration_')
        print_info(f"Output directory: {output_dir}\n")
    
    # Check BaSyx connection (unless dry run)
    if not args.dry_run:
        print_info("Checking BaSyx connection...")
        if not check_basyx_connection(args.basyx_url):
            print_failure("Cannot connect to BaSyx server. Exiting.")
            return 1
        print_success("BaSyx server is reachable\n")
    
    # Initialize service (unless dry run)
    service = None
    if not args.dry_run:
        try:
            config = BaSyxConfig(base_url=args.basyx_url)
            service = UnifiedRegistrationService(
                config=config,
                mqtt_broker=args.mqtt_broker,
                mqtt_port=args.mqtt_port,
                delegation_service_url=args.delegation_url
            )
            print_success("Registration service initialized\n")
        except Exception as e:
            print_failure(f"Failed to initialize service: {e}")
            return 1
    
    # Process each config file
    print_header("Processing Assets")
    
    results = {
        'total': len(config_files),
        'successful': [],
        'failed': [],
        'skipped': []
    }
    
    for idx, config_file in enumerate(config_files, 1):
        print_progress(idx, len(config_files), f"Processing {config_file.name}")
        print()
        
        if args.dry_run:
            # Just show what would be registered
            asset_info = get_asset_info(config_file)
            if 'error' in asset_info:
                print_failure(f"Cannot parse config: {asset_info['error']}")
                results['failed'].append(asset_info)
            else:
                print_info(f"Would register: {asset_info['id_short']}")
                print_info(f"  AAS ID: {asset_info['aas_id']}")
                results['skipped'].append(asset_info)
        else:
            # Actual registration
            success, result_info = register_asset(
                config_file,
                service,
                validate=args.validate,
                output_dir=output_dir
            )
            
            if success:
                results['successful'].append(result_info)
            else:
                results['failed'].append(result_info)
                if not args.continue_on_error:
                    print_failure("Stopping due to error (use --continue-on-error to continue)")
                    break
        
        print()  # Spacing between assets
    
    # Summary
    print_header("Registration Summary")
    
    if args.dry_run:
        print(f"{Colors.BOLD}Dry Run - No assets were actually registered{Colors.END}\n")
        print(f"Total configs found: {results['total']}")
        print(f"  Valid configs: {len(results['skipped'])}")
        print(f"  Invalid configs: {len(results['failed'])}")
    else:
        print(f"{Colors.BOLD}Total: {results['total']}{Colors.END}")
        print(f"{Colors.GREEN}Successful: {len(results['successful'])}{Colors.END}")
        print(f"{Colors.RED}Failed: {len(results['failed'])}{Colors.END}")
        print()
        
        if results['successful']:
            print(f"{Colors.BOLD}Successfully Registered Assets:{Colors.END}")
            for asset in results['successful']:
                print_success(f"{asset['id_short']} ({asset['file_name']})")
            print()
        
        if results['failed']:
            print(f"{Colors.BOLD}Failed Registrations:{Colors.END}")
            for asset in results['failed']:
                file_name = asset.get('file_name', 'unknown')
                error = asset.get('error', 'Unknown error')
                print_failure(f"{file_name}: {error}")
            print()
    
    # Show output directory if kept
    if args.keep_output and output_dir:
        print(f"{Colors.YELLOW}Output files kept at: {output_dir}{Colors.END}\n")
    
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
