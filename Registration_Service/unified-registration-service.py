#!/usr/bin/env python3
"""
Unified AAS Registration Service - CLI Entry Point

This service automatically:
1. Parses YAML configuration files to extract asset definitions
2. Generates Operation Delegation topics.json
3. Generates DataBridge configurations directly from config
4. Generates AAS descriptions using the AAS generator
5. Registers AAS and submodels with BaSyx server
6. Restarts services to apply changes

Usage:
    # Register from YAML config (preferred)
    python unified-registration-service.py register-config path/to/config.yaml
    
    # Register all configs from a directory
    python unified-registration-service.py register-dir path/to/configs/
    
    # Start MQTT listener for config-based registration
    python unified-registration-service.py listen
    
    # Generate only topics.json
    python unified-registration-service.py generate-topics path/to/configs/
    
    # Generate only DataBridge configs
    python unified-registration-service.py generate-databridge path/to/configs/
    
    # List registered AAS
    python unified-registration-service.py list
"""

import argparse
import logging
import sys
from pathlib import Path

from src import (
    BaSyxConfig,
    UnifiedRegistrationService,
    MQTTConfigRegistrationService,
    TopicsGenerator,
    DataBridgeFromConfig,
    generate_topics_from_directory,
    generate_databridge_from_directory,
    start_delegation_api_background,
    set_full_topic_config
)
from src.core.constants import (
    DEFAULT_MQTT_BROKER,
    DEFAULT_MQTT_PORT,
    DEFAULT_BASYX_URL,
    DEFAULT_DELEGATION_URL,
    ContainerNames,
    MQTTTopics
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description='Unified AAS Registration Service - Register assets from YAML configs',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Register from YAML config (preferred):
    %(prog)s register-config configs/planarShuttle1.yaml
  
  Register all configs from directory:
    %(prog)s register-dir AASDescriptions/Resource/configs/
  
  Start MQTT listener:
    %(prog)s listen --mqtt-broker 192.168.0.104
  
  Generate Operation Delegation topics.json:
    %(prog)s generate-topics AASDescriptions/Resource/configs/
  
  Generate DataBridge configs:
    %(prog)s generate-databridge AASDescriptions/Resource/configs/
  
  List registered AAS:
    %(prog)s list
        """
    )

    # Global options
    parser.add_argument('--basyx-url', default=DEFAULT_BASYX_URL,
                        help=f'BaSyx server base URL (default: {DEFAULT_BASYX_URL})')
    parser.add_argument('--mqtt-broker', default=DEFAULT_MQTT_BROKER,
                        help=f'MQTT broker hostname/IP (default: {DEFAULT_MQTT_BROKER})')
    parser.add_argument('--mqtt-port', type=int, default=DEFAULT_MQTT_PORT,
                        help=f'MQTT broker port (default: {DEFAULT_MQTT_PORT})')
    parser.add_argument('--delegation-url', default=DEFAULT_DELEGATION_URL,
                        help='Operation Delegation Service URL')
    parser.add_argument('--debug', action='store_true',
                        help='Enable debug logging')

    # Subcommands
    subparsers = parser.add_subparsers(
        dest='command', help='Command to execute')

    # Register from YAML config (primary command)
    config_parser = subparsers.add_parser('register-config',
                                          help='Register asset from YAML config file')
    config_parser.add_argument('config_file', type=str,
                               help='Path to YAML configuration file')
    config_parser.add_argument('--no-validate', action='store_true',
                               help='Skip AAS validation')
    config_parser.add_argument('--databridge-name', default=ContainerNames.DATABRIDGE,
                               help='DataBridge container name')
    config_parser.add_argument('--delegation-container', default=ContainerNames.OPERATION_DELEGATION,
                               help='Operation Delegation container name')

    # Register from directory
    dir_parser = subparsers.add_parser('register-dir',
                                       help='Register all assets from config directory')
    dir_parser.add_argument('config_dir', type=str,
                            help='Directory containing YAML config files')
    dir_parser.add_argument('--no-validate', action='store_true',
                            help='Skip AAS validation')
    dir_parser.add_argument('--databridge-name', default=ContainerNames.DATABRIDGE,
                            help='DataBridge container name')

    # Generate topics.json only
    topics_parser = subparsers.add_parser('generate-topics',
                                          help='Generate Operation Delegation topics.json')
    topics_parser.add_argument('config_dir', type=str,
                               help='Directory containing YAML config files')
    topics_parser.add_argument('--output', type=str,
                               help='Output path for topics.json')

    # Generate DataBridge configs only
    databridge_parser = subparsers.add_parser('generate-databridge',
                                              help='Generate DataBridge configurations')
    databridge_parser.add_argument('config_dir', type=str,
                                   help='Directory containing YAML config files')
    databridge_parser.add_argument('--output-dir', type=str, default='../databridge',
                                   help='Output directory for DataBridge configs')

    # MQTT Listener
    listen_parser = subparsers.add_parser('listen',
                                          help='Start MQTT listener for registration')
    listen_parser.add_argument('--config-topic', default=MQTTTopics.REGISTRATION_CONFIG,
                               help='MQTT topic for config registration')
    listen_parser.add_argument('--legacy-topic', default=MQTTTopics.REGISTRATION_LEGACY,
                               help='MQTT topic for legacy registration')
    listen_parser.add_argument('--response-topic', default=MQTTTopics.REGISTRATION_RESPONSE,
                               help='MQTT topic for responses')
    listen_parser.add_argument('--databridge-name', default=ContainerNames.DATABRIDGE,
                               help='DataBridge container name')
    listen_parser.add_argument('--delegation-port', type=int, default=8087,
                               help='Port for Operation Delegation HTTP API (default: 8087)')
    listen_parser.add_argument('--topics-json', type=str,
                               help='Path to existing topics.json to load at startup')

    # List registered AAS
    list_parser = subparsers.add_parser('list', help='List all registered AAS')

    # Configure
    configure_parser = subparsers.add_parser('configure',
                                             help='Show/update configuration')

    args = parser.parse_args()

    # Set logging level
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    # Validate command
    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        # Initialize BaSyx configuration
        basyx_config = BaSyxConfig(base_url=args.basyx_url)

        # Execute command
        if args.command == 'register-config':
            # Register from YAML config
            config_path = Path(args.config_file)
            if not config_path.exists():
                logger.error(f"Config file not found: {config_path}")
                sys.exit(1)

            service = UnifiedRegistrationService(
                config=basyx_config,
                mqtt_broker=args.mqtt_broker,
                mqtt_port=args.mqtt_port,
                databridge_container_name=args.databridge_name,
                operation_delegation_container=args.delegation_container,
                delegation_service_url=args.delegation_url
            )

            logger.info(f"Registering from config: {config_path}")
            success = service.register_from_yaml_config(
                config_path=str(config_path),
                validate_aas=not args.no_validate
            )

            if success:
                logger.info("✓ Registration completed successfully")
                sys.exit(0)
            else:
                logger.error("✗ Registration failed")
                sys.exit(1)

        elif args.command == 'register-dir':
            # Register from directory
            config_dir = Path(args.config_dir)
            if not config_dir.exists():
                logger.error(f"Config directory not found: {config_dir}")
                sys.exit(1)

            config_paths = list(config_dir.glob('*.yaml')) + \
                list(config_dir.glob('*.yml'))
            if not config_paths:
                logger.error(f"No YAML files found in {config_dir}")
                sys.exit(1)

            service = UnifiedRegistrationService(
                config=basyx_config,
                mqtt_broker=args.mqtt_broker,
                mqtt_port=args.mqtt_port,
                databridge_container_name=args.databridge_name,
                delegation_service_url=args.delegation_url
            )

            logger.info(
                f"Registering {len(config_paths)} configs from {config_dir}")
            results = service.register_multiple_configs(
                [str(p) for p in config_paths],
                validate_aas=not args.no_validate
            )

            successful = sum(1 for s in results.values() if s)
            if successful == len(results):
                logger.info(f"✓ All {successful} registrations completed")
                sys.exit(0)
            elif successful > 0:
                logger.warning(
                    f"⚠ {successful}/{len(results)} registrations completed")
                sys.exit(0)
            else:
                logger.error("✗ All registrations failed")
                sys.exit(1)

        elif args.command == 'generate-topics':
            # Generate topics.json only
            config_dir = Path(args.config_dir)
            if not config_dir.exists():
                logger.error(f"Config directory not found: {config_dir}")
                sys.exit(1)

            output_path = args.output if args.output else None
            success = generate_topics_from_directory(
                str(config_dir), output_path)

            if success:
                logger.info("✓ topics.json generated successfully")
                sys.exit(0)
            else:
                logger.error("✗ Failed to generate topics.json")
                sys.exit(1)

        elif args.command == 'generate-databridge':
            # Generate DataBridge configs only
            config_dir = Path(args.config_dir)
            if not config_dir.exists():
                logger.error(f"Config directory not found: {config_dir}")
                sys.exit(1)

            output_dir = args.output_dir
            counts = generate_databridge_from_directory(
                str(config_dir),
                output_dir,
                args.mqtt_broker,
                args.mqtt_port,
                f"http://aas-env:{args.basyx_url.split(':')[-1].rstrip('/')}"
            )

            if counts:
                logger.info(f"✓ DataBridge configs generated:")
                logger.info(f"  - {counts.get('consumers', 0)} consumers")
                logger.info(
                    f"  - {counts.get('transformers', 0)} transformers")
                logger.info(f"  - {counts.get('sinks', 0)} sinks")
                logger.info(f"  - {counts.get('routes', 0)} routes")
                sys.exit(0)
            else:
                logger.error("✗ Failed to generate DataBridge configs")
                sys.exit(1)

        elif args.command == 'listen':
            # Always load existing topics.json for persistence across restarts
            # Default path is /app/config/topics.json in container
            default_topics_path = Path('/app/config/topics.json')
            topics_path = Path(args.topics_json) if args.topics_json else default_topics_path
            
            if topics_path.exists():
                import json
                try:
                    with open(topics_path, 'r') as f:
                        existing_config = json.load(f)
                    set_full_topic_config(existing_config)
                    logger.info(f"Loaded {len(existing_config)} topic configs from {topics_path}")
                except Exception as e:
                    logger.warning(f"Failed to load topics.json: {e}")
            else:
                logger.info(f"No existing topics.json found at {topics_path} - starting with empty config")
            
            # Start Operation Delegation Flask API in background thread
            logger.info(f"Starting Operation Delegation API on port {args.delegation_port}...")
            start_delegation_api_background(
                host='0.0.0.0',
                port=args.delegation_port,
                mqtt_broker=args.mqtt_broker,
                mqtt_port=args.mqtt_port
            )
            logger.info(f"✓ Operation Delegation API running on http://0.0.0.0:{args.delegation_port}")
            
            # Start MQTT listener
            service = UnifiedRegistrationService(
                config=basyx_config,
                mqtt_broker=args.mqtt_broker,
                mqtt_port=args.mqtt_port,
                databridge_container_name=args.databridge_name,
                delegation_service_url=args.delegation_url
            )

            mqtt_service = MQTTConfigRegistrationService(
                registration_service=service,
                mqtt_broker=args.mqtt_broker,
                mqtt_port=args.mqtt_port,
                config_topic=args.config_topic,
                legacy_topic=args.legacy_topic,
                response_topic=args.response_topic
            )

            logger.info("Starting MQTT registration listener...")
            logger.info(f"MQTT Broker: {args.mqtt_broker}:{args.mqtt_port}")
            logger.info(f"Config Topic: {args.config_topic}")
            logger.info(f"Legacy Topic: {args.legacy_topic}")
            logger.info(f"Delegation API: http://0.0.0.0:{args.delegation_port}")

            try:
                mqtt_service.start()
                logger.info("✓ MQTT listener started. Press Ctrl+C to stop.")
                logger.info("\nUnified Service running with:")
                logger.info("  - MQTT registration listener")
                logger.info(f"  - Operation Delegation API on port {args.delegation_port}")
                logger.info("\nSupported config message formats:")
                logger.info("1. Raw YAML (from ESP32 devices):")
                logger.info("   syntegonStopperingSystemAAS:")
                logger.info("     idShort: syntegonStopperingSystemAAS")
                logger.info("     ...")
                logger.info("")
                logger.info("2. JSON wrapper (from other clients):")
                logger.info('{')
                logger.info('  "requestId": "unique-id",')
                logger.info('  "assetId": "asset-identifier",')
                logger.info('  "config": { ... yaml config as JSON ... }')
                logger.info('}\n')

                while True:
                    import time
                    time.sleep(1)

            except KeyboardInterrupt:
                logger.info("\nShutting down...")
                mqtt_service.stop()

                stats = mqtt_service.get_stats()
                logger.info(f"\nStatistics:")
                logger.info(f"  Config received: {stats['config_received']}")
                logger.info(f"  Legacy received: {stats['legacy_received']}")
                logger.info(f"  Processed: {stats['processed']}")
                logger.info(f"  Failed: {stats['failed']}")

                sys.exit(0)

        elif args.command == 'list':
            service = UnifiedRegistrationService(
                config=basyx_config,
                mqtt_broker=args.mqtt_broker,
                mqtt_port=args.mqtt_port
            )

            registered = service.list_registered_assets()
            shells = registered.get('aas_shells', [])
            submodels = registered.get('submodels', [])

            if shells:
                logger.info(f"\nRegistered AAS Shells ({len(shells)}):")
                for shell in shells:
                    logger.info(f"  • {shell.get('idShort', 'Unknown')}")
                    logger.info(f"    ID: {shell.get('id', 'Unknown')}")
            else:
                logger.info("\nNo AAS shells registered")

            if submodels:
                logger.info(f"\nRegistered Submodels ({len(submodels)}):")
                for sm in submodels:
                    logger.info(f"  • {sm.get('idShort', 'Unknown')}")

            sys.exit(0)

        elif args.command == 'configure':
            logger.info("Current configuration:")
            logger.info(f"  BaSyx URL: {args.basyx_url}")
            logger.info(f"  MQTT Broker: {args.mqtt_broker}:{args.mqtt_port}")
            logger.info(f"  Delegation URL: {args.delegation_url}")
            sys.exit(0)

        else:
            parser.print_help()
            sys.exit(1)

    except KeyboardInterrupt:
        logger.info("\nOperation cancelled")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=args.debug)
        sys.exit(1)


if __name__ == "__main__":
    main()
