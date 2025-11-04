#!/usr/bin/env python3
"""
BaSyx AAS Registration Service - CLI Entry Point

This service automatically:
1. Parses AASX files or JSON to extract AAS and submodel definitions
2. Registers AAS and submodels with BaSyx server
3. Auto-generates BaSyx Databridge configurations for MQTT integration
4. Sets up property mappings and routes with custom topic bindings
5. Restarts the databridge container to apply changes

Usage:
    python aas-registration-service.py register path/to/file.aasx
    python aas-registration-service.py register-json path/to/registration.json
    python aas-registration-service.py configure --mqtt-broker 192.168.0.104
    python aas-registration-service.py list
"""

import argparse
import logging
import sys
from pathlib import Path

from src import BaSyxConfig, BaSyxRegistrationService

# Configure logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description='BaSyx AAS Registration Service - Register and manage Asset Administration Shells',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Register an AASX file:
    %(prog)s register path/to/file.aasx
  
  Register from JSON with custom topics:
    %(prog)s register-json robot_registration.json
  
  Configure MQTT broker:
    %(prog)s configure --mqtt-broker 192.168.0.104
  
  List registered AAS:
    %(prog)s list
        """
    )

    # Global options
    parser.add_argument('--basyx-url', default='http://localhost:8081',
                        help='BaSyx server base URL (default: http://localhost:8081)')
    parser.add_argument('--debug', action='store_true',
                        help='Enable debug logging')

    # Subcommands
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')

    # Register AASX command
    register_parser = subparsers.add_parser('register',
                                            help='Register an AASX file with BaSyx')
    register_parser.add_argument('aasx_file', type=str,
                                 help='Path to AASX file')
    register_parser.add_argument('--mqtt-broker', type=str,
                                 help='MQTT broker hostname/IP (default: hivemq-broker)')
    register_parser.add_argument('--mqtt-port', type=int, default=1883,
                                 help='MQTT broker port (default: 1883)')
    register_parser.add_argument('--databridge-name', type=str, default='databridge',
                                 help='Name of databridge container (default: databridge)')

    # Register from JSON command
    register_json_parser = subparsers.add_parser('register-json',
                                                  help='Register from JSON file with custom topics')
    register_json_parser.add_argument('json_file', type=str,
                                      help='Path to JSON registration file')
    register_json_parser.add_argument('--mqtt-broker', type=str,
                                      help='MQTT broker hostname/IP (default: hivemq-broker)')
    register_json_parser.add_argument('--mqtt-port', type=int, default=1883,
                                      help='MQTT broker port (default: 1883)')
    register_json_parser.add_argument('--databridge-name', type=str, default='databridge',
                                      help='Name of databridge container (default: databridge)')

    # List command
    list_parser = subparsers.add_parser('list',
                                        help='List all registered AAS')

    # Configure command
    config_parser = subparsers.add_parser('configure',
                                          help='Configure service settings')
    config_parser.add_argument('--mqtt-broker', type=str,
                               help='MQTT broker hostname/IP')
    config_parser.add_argument('--mqtt-port', type=int,
                               help='MQTT broker port')
    config_parser.add_argument('--databridge-name', type=str,
                               help='Name of databridge container')

    args = parser.parse_args()

    # Set logging level
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    # Validate command
    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        # Initialize configuration
        config = BaSyxConfig(base_url=args.basyx_url)

        # Initialize service
        service = BaSyxRegistrationService(
            config=config,
            mqtt_broker=getattr(args, 'mqtt_broker', 'hivemq-broker'),
            mqtt_port=getattr(args, 'mqtt_port', 1883),
            databridge_container_name=getattr(args, 'databridge_name', 'databridge')
        )

        # Execute command
        if args.command == 'register':
            aasx_path = Path(args.aasx_file)
            if not aasx_path.exists():
                logger.error(f"AASX file not found: {aasx_path}")
                sys.exit(1)

            logger.info(f"Registering AASX file: {aasx_path}")
            success = service.register_aasx(str(aasx_path))

            if success:
                logger.info("✓ Registration completed successfully")
                sys.exit(0)
            else:
                logger.error("✗ Registration failed")
                sys.exit(1)

        elif args.command == 'register-json':
            json_path = Path(args.json_file)
            if not json_path.exists():
                logger.error(f"JSON file not found: {json_path}")
                sys.exit(1)

            logger.info(f"Registering from JSON: {json_path}")
            success = service.register_from_json(str(json_path))

            if success:
                logger.info("✓ JSON registration completed successfully")
                sys.exit(0)
            else:
                logger.error("✗ JSON registration failed")
                sys.exit(1)

        elif args.command == 'list':
            logger.info("Listing all registered AAS shells...")
            shells = service.list_shells()

            if shells:
                logger.info(f"\nFound {len(shells)} registered AAS shell(s):\n")
                for shell in shells:
                    shell_id = shell.get('id', 'Unknown')
                    id_short = shell.get('idShort', 'Unknown')
                    logger.info(f"  • {id_short}")
                    logger.info(f"    ID: {shell_id}")

                    # Show submodels
                    submodels = shell.get('submodels', [])
                    if submodels:
                        logger.info(f"    Submodels: {len(submodels)}")
                        for sm in submodels:
                            sm_keys = sm.get('keys', [])
                            if sm_keys:
                                sm_id = sm_keys[0].get('value', 'Unknown')
                                logger.info(f"      - {sm_id}")
                    logger.info("")
            else:
                logger.info("No AAS shells registered")

            sys.exit(0)

        elif args.command == 'configure':
            logger.info("Updating configuration...")

            if args.mqtt_broker:
                service.mqtt_broker = args.mqtt_broker
                logger.info(f"MQTT broker: {args.mqtt_broker}")

            if args.mqtt_port:
                service.mqtt_port = args.mqtt_port
                logger.info(f"MQTT port: {args.mqtt_port}")

            if args.databridge_name:
                service.databridge_container_name = args.databridge_name
                logger.info(f"Databridge container: {args.databridge_name}")

            logger.info("✓ Configuration updated")
            sys.exit(0)

        else:
            parser.print_help()
            sys.exit(1)

    except KeyboardInterrupt:
        logger.info("\nOperation cancelled by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=args.debug)
        sys.exit(1)


if __name__ == "__main__":
    main()
