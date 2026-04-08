#!/usr/bin/env python3
"""
Registration Service Integration Test

Tests all components of the registration flow:
1. Config parsing
2. Topics.json generation
3. DataBridge config generation
4. AAS generation
5. Full registration (optional - requires BaSyx)

Usage:
    python test_registration_flow.py
    python test_registration_flow.py --with-basyx --basyx-url http://localhost:8081
"""

from src import (
    ConfigParser,
    TopicsGenerator,
    DataBridgeFromConfig,
    AASGenerator,
    AASValidator,
    UnifiedRegistrationService,
    BaSyxConfig
)
import sys
import os
import json
import tempfile
import shutil
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class Colors:
    """ANSI color codes for terminal output"""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'


def print_header(text):
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.END}\n")


def print_success(text):
    print(f"{Colors.GREEN}✓ {text}{Colors.END}")


def print_failure(text):
    print(f"{Colors.RED}✗ {text}{Colors.END}")


def print_info(text):
    print(f"{Colors.YELLOW}  → {text}{Colors.END}")


def test_config_parsing(config_path: str) -> dict:
    """Test 1: Parse YAML config"""
    print_header("TEST 1: Config Parsing")

    try:
        parser = ConfigParser(config_path=config_path)

        # Test basic info extraction
        id_short = parser.id_short
        print_success(f"idShort: {id_short}")

        aas_id = parser.aas_id
        print_success(f"aasId: {aas_id}")

        global_asset_id = parser.global_asset_id
        print_success(f"globalAssetId: {global_asset_id}")

        # Test MQTT endpoint
        mqtt = parser.get_mqtt_endpoint()
        print_success(f"MQTT base topic: {mqtt.get('base_topic')}")
        print_info(
            f"Broker: {mqtt.get('broker_host')}:{mqtt.get('broker_port')}")

        # Test actions
        actions = parser.get_actions()
        print_success(f"Actions found: {len(actions)}")
        for action in actions:
            name = list(action.keys())[0] if isinstance(
                action, dict) else action.get('name', 'unknown')
            print_info(f"- {name}")

        # Test properties
        properties = parser.get_properties()
        print_success(f"Properties found: {len(properties)}")
        for prop in properties:
            name = list(prop.keys())[0] if isinstance(
                prop, dict) else prop.get('name', 'unknown')
            print_info(f"- {name}")

        # Test operation delegation entry
        delegation = parser.get_operation_delegation_entry()
        skills = delegation.get('skills', {})
        print_success(f"Delegation entry generated with {len(skills)} skills")
        for skill_name in skills:
            print_info(f"- {skill_name}")

        return {
            'parser': parser,
            'id_short': id_short,
            'actions': actions,
            'properties': properties,
            'status': 'PASSED'
        }

    except Exception as e:
        print_failure(f"Config parsing failed: {e}")
        import traceback
        traceback.print_exc()
        return {'status': 'FAILED', 'error': str(e)}


def test_topics_generation(config_path: str, output_dir: str) -> dict:
    """Test 2: Generate topics.json"""
    print_header("TEST 2: Topics.json Generation")

    try:
        output_path = os.path.join(output_dir, 'topics.json')

        generator = TopicsGenerator(output_path)

        # Use add_from_config_file which accepts a path
        success = generator.add_from_config_file(config_path)
        if not success:
            print_failure("Failed to add config to topics generator")

        generator.save()

        # Verify output
        with open(output_path, 'r') as f:
            topics = json.load(f)

        print_success(f"topics.json created at {output_path}")
        print_info(f"Assets in topics.json: {len(topics)}")

        for asset_id, asset_data in topics.items():
            print_info(f"- {asset_id}:")
            print_info(f"    base_topic: {asset_data.get('base_topic')}")
            skills = asset_data.get('skills', {})
            print_info(f"    skills: {len(skills)}")
            for skill_name, skill_data in skills.items():
                print_info(f"      • {skill_name}")

        return {
            'topics': topics,
            'output_path': output_path,
            'status': 'PASSED' if topics else 'FAILED'
        }

    except Exception as e:
        print_failure(f"Topics generation failed: {e}")
        import traceback
        traceback.print_exc()
        return {'status': 'FAILED', 'error': str(e)}


def test_databridge_generation(config_path: str, output_dir: str) -> dict:
    """Test 3: Generate DataBridge configs"""
    print_header("TEST 3: DataBridge Config Generation")

    try:
        generator = DataBridgeFromConfig(
            mqtt_broker="hivemq-broker",
            mqtt_port=1883
        )

        # Use add_from_config_file which accepts a path
        success = generator.add_from_config_file(config_path)
        if not success:
            print_failure("Failed to add config to DataBridge generator")

        counts = generator.save_configs(output_dir)

        print_success(f"DataBridge configs generated in {output_dir}")
        print_info(f"Consumers: {counts.get('consumers', 0)}")
        print_info(f"Transformers: {counts.get('transformers', 0)}")
        print_info(f"Sinks: {counts.get('sinks', 0)}")
        print_info(f"Routes: {counts.get('routes', 0)}")

        # Show sample files
        for filename in ['mqttconsumer.json', 'jsonatatransformer.json', 'aasserver.json', 'routes.json']:
            filepath = os.path.join(output_dir, filename)
            if os.path.exists(filepath):
                with open(filepath, 'r') as f:
                    content = json.load(f)
                print_info(f"{filename}: {len(content)} entries")

        return {
            'counts': counts,
            'output_dir': output_dir,
            'status': 'PASSED' if counts.get('routes', 0) > 0 else 'PASSED_WITH_WARNINGS'
        }

    except Exception as e:
        print_failure(f"DataBridge generation failed: {e}")
        import traceback
        traceback.print_exc()
        return {'status': 'FAILED', 'error': str(e)}


def test_aas_generation(config_path: str, output_dir: str) -> dict:
    """Test 4: Generate AAS"""
    print_header("TEST 4: AAS Generation")

    try:
        generator = AASGenerator(
            config_path=config_path,
            delegation_base_url="http://registration-service:8087"
        )

        # Load config to get system_id
        import yaml
        with open(config_path, 'r') as f:
            config_data = yaml.safe_load(f)
        system_id = list(config_data.keys())[0]
        system_config = config_data[system_id]

        # Generate AAS for this system - returns dict when return_store=False
        aas_data = generator.generate_system(
            system_id, system_config, return_store=False)

        # Count components
        shells = aas_data.get('assetAdministrationShells', [])
        submodels = aas_data.get('submodels', [])
        concepts = aas_data.get('conceptDescriptions', [])

        print_success(f"AAS generated successfully")
        print_info(f"Shells: {len(shells)}")
        print_info(f"Submodels: {len(submodels)}")
        print_info(f"Concept Descriptions: {len(concepts)}")

        # Show shell info
        for shell in shells:
            print_info(f"Shell: {shell.get('idShort')} ({shell.get('id')})")

        # Show submodel info
        for sm in submodels:
            sm_elements = sm.get('submodelElements', [])
            print_info(
                f"Submodel: {sm.get('idShort')} - {len(sm_elements)} elements")

        output_path = os.path.join(output_dir, 'aas_output.json')
        with open(output_path, 'w') as f:
            json.dump(aas_data, f, indent=2)
        print_success(f"AAS saved to {output_path}")

        # Basic validation - check required components exist
        print_info("Running basic validation...")
        is_valid = True
        errors = []

        if len(shells) == 0:
            errors.append("No AAS shells generated")
            is_valid = False
        if len(submodels) == 0:
            errors.append("No submodels generated")
            is_valid = False

        # Check shell has required fields
        for shell in shells:
            if not shell.get('id'):
                errors.append("Shell missing 'id'")
                is_valid = False
            if not shell.get('idShort'):
                errors.append("Shell missing 'idShort'")
                is_valid = False

        if is_valid:
            print_success("Basic validation passed")
        else:
            print_failure(f"Validation found {len(errors)} issues")
            for error in errors:
                print_info(f"  - {error}")

        return {
            'shell': shell,
            'submodels': submodels,
            'output_path': output_path,
            'valid': is_valid,
            'status': 'PASSED' if is_valid else 'PASSED_WITH_WARNINGS'
        }

    except Exception as e:
        print_failure(f"AAS generation failed: {e}")
        import traceback
        traceback.print_exc()
        return {'status': 'FAILED', 'error': str(e)}


def test_full_registration(config_path: str, basyx_url: str, output_dir: str) -> dict:
    """Test 5: Full registration with BaSyx (optional)"""
    print_header("TEST 5: Full Registration Flow")

    try:
        # Check if BaSyx is reachable
        import requests
        try:
            response = requests.get(f"{basyx_url}/shells", timeout=5)
            if response.status_code not in [200, 401]:
                print_info(f"BaSyx returned status {response.status_code}")
        except requests.exceptions.ConnectionError:
            print_failure(f"Cannot connect to BaSyx at {basyx_url}")
            print_info("Skipping full registration test")
            return {'status': 'SKIPPED', 'reason': 'BaSyx not reachable'}

        print_success(f"BaSyx reachable at {basyx_url}")

        # Initialize service
        config = BaSyxConfig(base_url=basyx_url)
        service = UnifiedRegistrationService(
            config=config,
            mqtt_broker="192.168.0.104",
            mqtt_port=1883,
            delegation_service_url="http://192.168.0.104:8087"
        )

        # Run registration
        print_info("Starting registration...")
        success = service.register_from_yaml_config(
            config_path=config_path,
            validate_aas=True
        )

        if success:
            print_success("Registration completed successfully")

            # Verify registration
            registered = service.list_registered_assets()
            shells = registered.get('aas_shells', [])
            print_info(f"Total registered shells: {len(shells)}")

            return {'status': 'PASSED', 'registered': True}
        else:
            print_failure("Registration failed")
            return {'status': 'FAILED', 'registered': False}

    except Exception as e:
        print_failure(f"Full registration failed: {e}")
        import traceback
        traceback.print_exc()
        return {'status': 'FAILED', 'error': str(e)}


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Test Registration Service Flow')
    parser.add_argument('--config', default='tests/test_config.yaml',
                        help='Path to test config file')
    parser.add_argument('--with-basyx', action='store_true',
                        help='Include full BaSyx registration test')
    parser.add_argument('--basyx-url', default='http://aas-env:8081',
                        help='BaSyx server URL (default: http://aas-env:8081 for Docker)')
    parser.add_argument('--keep-output', action='store_true',
                        help='Keep test output directory')
    args = parser.parse_args()

    # Resolve config path
    script_dir = Path(__file__).parent.parent
    config_path = script_dir / args.config

    if not config_path.exists():
        print_failure(f"Config file not found: {config_path}")
        sys.exit(1)

    print(f"\n{Colors.BOLD}Registration Service Integration Test{Colors.END}")
    print(f"Config: {config_path}")
    print(f"BaSyx: {args.basyx_url if args.with_basyx else 'Skipped'}")

    # Create temp output directory
    output_dir = tempfile.mkdtemp(prefix='reg_test_')
    print(f"Output: {output_dir}\n")

    results = {}

    try:
        # Run tests
        results['config_parsing'] = test_config_parsing(str(config_path))
        results['topics_generation'] = test_topics_generation(
            str(config_path), output_dir)
        results['databridge_generation'] = test_databridge_generation(
            str(config_path), output_dir)
        results['aas_generation'] = test_aas_generation(
            str(config_path), output_dir)

        if args.with_basyx:
            results['full_registration'] = test_full_registration(
                str(config_path), args.basyx_url, output_dir
            )

        # Summary
        print_header("TEST SUMMARY")

        passed = 0
        failed = 0
        skipped = 0

        for test_name, result in results.items():
            status = result.get('status', 'UNKNOWN')
            if status == 'PASSED':
                print_success(f"{test_name}: PASSED")
                passed += 1
            elif status == 'PASSED_WITH_WARNINGS':
                print(
                    f"{Colors.YELLOW}⚠ {test_name}: PASSED WITH WARNINGS{Colors.END}")
                passed += 1
            elif status == 'SKIPPED':
                print_info(f"{test_name}: SKIPPED")
                skipped += 1
            else:
                print_failure(f"{test_name}: FAILED")
                failed += 1

        print(
            f"\n{Colors.BOLD}Results: {passed} passed, {failed} failed, {skipped} skipped{Colors.END}")

        # Show output files
        print(f"\n{Colors.BOLD}Generated Files:{Colors.END}")
        for f in os.listdir(output_dir):
            filepath = os.path.join(output_dir, f)
            size = os.path.getsize(filepath)
            print(f"  {f}: {size} bytes")

        if args.keep_output:
            print(f"\n{Colors.YELLOW}Output kept at: {output_dir}{Colors.END}")

        return 0 if failed == 0 else 1

    finally:
        if not args.keep_output:
            shutil.rmtree(output_dir, ignore_errors=True)


if __name__ == '__main__':
    sys.exit(main())
