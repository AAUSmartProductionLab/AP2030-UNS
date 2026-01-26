#!/usr/bin/env python3
"""
Test script for the planning package.

This script tests the planning modules using real AAS data from BaSyx.
It queries the AAS server to validate the capability matching, BT generation, 
and process AAS generation.
"""

from planning.planner_service import PlannerService, PlannerConfig
from planning.process_aas_generator import ProcessAASGenerator
from planning.bt_generator import BTGenerator, BTGeneratorConfig
from planning.capability_matcher import CapabilityMatcher, ProcessStep
from aas_client import AASClient
import os
import sys
import json
from dataclasses import asdict

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# BaSyx server configuration
AAS_SERVER_URL = os.getenv("AAS_SERVER_URL", "http://192.168.0.104:8081")
AAS_REGISTRY_URL = os.getenv("AAS_REGISTRY_URL", "http://192.168.0.104:8082")


def test_aas_connection():
    """Test AAS server connectivity"""
    print("=" * 60)
    print("Testing AAS Server Connectivity")
    print("=" * 60)

    client = AASClient(AAS_SERVER_URL, AAS_REGISTRY_URL)

    # List all shells
    shells = client.get_all_aas()
    print(f"\nFound {len(shells)} AAS shells:")
    for shell in shells[:10]:  # Show first 10
        print(f"  - {shell.id_short}: {shell.id}")

    if len(shells) > 10:
        print(f"  ... and {len(shells) - 10} more")

    return client


def test_product_aas_structure(client: AASClient, product_aas_id: str):
    """Test fetching and parsing product AAS structure"""
    print("\n" + "=" * 60)
    print(f"Testing Product AAS Structure: {product_aas_id}")
    print("=" * 60)

    # Get the AAS
    shell = client.get_aas_by_id(product_aas_id)
    if not shell:
        print(f"ERROR: Could not find AAS: {product_aas_id}")
        return None

    print(f"\nAAS: {shell.id_short}")
    print(f"  ID: {shell.id}")
    print(
        f"  Asset Type: {shell.asset_information.asset_type if shell.asset_information else 'N/A'}")

    # Get submodels
    submodels = client.get_submodels_from_aas(product_aas_id)
    print(f"\nSubmodels ({len(submodels)}):")

    bill_of_processes = None
    for sm in submodels:
        print(f"  - {sm.id_short}: {sm.id}")
        if 'billofprocess' in sm.id_short.lower():
            bill_of_processes = sm

    return bill_of_processes


def test_bill_of_processes_parsing(client: AASClient, product_aas_id: str):
    """Test parsing BillOfProcesses from product AAS"""
    print("\n" + "=" * 60)
    print("Testing BillOfProcesses Parsing")
    print("=" * 60)

    # Create planner service
    config = PlannerConfig(
        aas_server_url=AAS_SERVER_URL,
        aas_registry_url=AAS_REGISTRY_URL,
        save_intermediate_files=False
    )
    planner = PlannerService(client, config=config)

    # Fetch product config
    product_config = planner._fetch_product_config(product_aas_id)

    if not product_config:
        print(f"ERROR: Could not fetch product config for {product_aas_id}")
        return None, None

    print(f"\nProduct: {product_config.get('idShort', 'Unknown')}")
    print(f"ID: {product_config.get('id', 'Unknown')}")

    # Extract process steps
    process_steps = planner.capability_matcher.extract_process_steps(
        product_config)

    print(f"\nProcess Steps ({len(process_steps)}):")
    for step in process_steps:
        print(f"  {step.step}. {step.name}")
        print(f"     Semantic ID: {step.semantic_id}")
        print(f"     Description: {step.description}")
        print(f"     Duration: {step.estimated_duration}s")

    # Extract requirements
    requirements = planner.capability_matcher.extract_requirements(
        product_config)

    print(f"\nRequirements:")
    print(
        f"  Environmental: {list(requirements.get('environmental', {}).keys())}")
    print(
        f"  In-Process Control: {list(requirements.get('in_process_control', {}).keys())}")
    print(
        f"  Quality Control: {list(requirements.get('quality_control', {}).keys())}")

    return process_steps, requirements


def test_resource_capabilities(client: AASClient, resource_aas_ids: list):
    """Test fetching resource capabilities"""
    print("\n" + "=" * 60)
    print("Testing Resource Capability Extraction")
    print("=" * 60)

    # Create planner service
    config = PlannerConfig(
        aas_server_url=AAS_SERVER_URL,
        aas_registry_url=AAS_REGISTRY_URL,
        save_intermediate_files=False
    )
    planner = PlannerService(client, config=config)

    # Resolve hierarchies
    print(f"\nInitial resource IDs: {len(resource_aas_ids)}")
    all_resources = planner._resolve_asset_hierarchies(resource_aas_ids)
    print(f"Resolved to {len(all_resources)} resources")

    # Fetch capabilities
    resources_with_caps = planner._fetch_resource_capabilities(all_resources)

    print(f"\nResources with capabilities:")
    for resource in resources_with_caps:
        caps = resource.get('capabilities', [])
        print(f"\n  {resource['name']} ({resource['aas_id']})")
        print(f"  Asset Type: {resource.get('asset_type', 'N/A')}")
        if caps:
            print(f"  Capabilities ({len(caps)}):")
            for cap in caps:
                print(f"    - {cap['name']}")
                if cap.get('semantic_id'):
                    print(f"      Semantic ID: {cap['semantic_id']}")
                if cap.get('realized_by'):
                    print(f"      Realized by skill: {cap['realized_by']}")
        else:
            print(f"  Capabilities: None")

    return resources_with_caps


def test_capability_matching(client: AASClient, product_aas_id: str, resource_aas_ids: list):
    """Test capability matching with real AAS data"""
    print("\n" + "=" * 60)
    print("Testing Capability Matching")
    print("=" * 60)

    # Create planner service
    config = PlannerConfig(
        aas_server_url=AAS_SERVER_URL,
        aas_registry_url=AAS_REGISTRY_URL,
        save_intermediate_files=False
    )
    planner = PlannerService(client, config=config)

    # Get product config and process steps
    product_config = planner._fetch_product_config(product_aas_id)
    if not product_config:
        print(f"ERROR: Could not fetch product config")
        return None

    process_steps = planner.capability_matcher.extract_process_steps(
        product_config)

    # Resolve resources and get capabilities
    all_resource_ids = planner._resolve_asset_hierarchies(resource_aas_ids)
    available_resources = planner._fetch_resource_capabilities(
        all_resource_ids)

    # Perform matching
    result = planner.capability_matcher.match_capabilities(
        process_steps, available_resources)

    print(f"\nMatching Results:")
    print(f"  Total process steps: {len(process_steps)}")
    print(
        f"  Matched steps: {len(process_steps) - len(result.unmatched_steps)}")
    print(f"  Unmatched steps: {len(result.unmatched_steps)}")
    print(f"  Movers found: {len(result.movers)}")
    print(f"  Parallelism factor: {result.parallelism_factor}")
    print(f"  Is complete: {result.is_complete}")

    print("\nProcess Matches:")
    for match in result.process_matches:
        status = "✓" if match.is_matched else "✗"
        resource = match.primary_resource.resource_name if match.primary_resource else "None"
        print(f"  {status} {match.process_step.name} -> {resource}")
        if match.is_matched:
            print(
                f"      Matched via semantic ID: {match.process_step.semantic_id}")

    if result.unmatched_steps:
        print("\nUnmatched Steps:")
        for step in result.unmatched_steps:
            print(f"  ✗ {step.name} (semantic ID: {step.semantic_id})")

    print("\nMovers:")
    for mover in result.movers:
        print(f"  - {mover.name} ({mover.aas_id})")

    return result, product_config


def test_bt_generation(matching_result, product_config: dict):
    """Test behavior tree generation"""
    print("\n" + "=" * 60)
    print("Testing Behavior Tree Generation")
    print("=" * 60)

    # Create BT generator with test config
    config = BTGeneratorConfig(
        subtrees_dir="../BTDescriptions",
        use_prebuilt_subtrees=False  # Don't try to load files in test
    )
    generator = BTGenerator(config)

    # Generate BT
    bt_xml = generator.generate_production_bt(
        matching_result,
        product_config,
        planar_table_id="https://smartproductionlab.aau.dk/aas/planarTableAAS"
    )

    print("\nGenerated Behavior Tree (first 2000 chars):")
    print("-" * 40)
    print(bt_xml[:2000])
    if len(bt_xml) > 2000:
        print(f"\n... ({len(bt_xml) - 2000} more characters)")

    # Get blackboard parameters
    params = generator.get_blackboard_parameters(
        matching_result,
        planar_table_id="https://smartproductionlab.aau.dk/aas/planarTableAAS"
    )

    print("\nBlackboard Parameters:")
    for key, value in params.items():
        print(f"  {key}: {value}")

    return bt_xml


def test_process_aas_generation(matching_result, product_config: dict, requirements: dict):
    """Test Process AAS configuration generation"""
    print("\n" + "=" * 60)
    print("Testing Process AAS Generation")
    print("=" * 60)

    generator = ProcessAASGenerator()

    product_aas_id = product_config.get('id', '')

    # Generate config
    config = generator.generate_config(
        matching_result,
        product_aas_id,
        product_config,
        requirements,
        "production_HgH.xml"
    )

    system_id = generator.get_system_id(config)
    aas_id = generator.get_aas_id(config)

    print(f"\nGenerated Process AAS:")
    print(f"  System ID: {system_id}")
    print(f"  AAS ID: {aas_id}")

    # Convert to YAML for display
    yaml_content = generator.config_to_yaml(config)
    print("\nYAML Configuration (first 2000 chars):")
    print("-" * 40)
    print(yaml_content[:2000])
    if len(yaml_content) > 2000:
        print(f"\n... ({len(yaml_content) - 2000} more characters)")

    return config


def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("Production Planning Package Test Suite")
    print(f"Using AAS Server: {AAS_SERVER_URL}")
    print("=" * 60)

    # Test AAS IDs
    product_aas_id = "https://smartproductionlab.aau.dk/aas/HgHAAS"
    resource_aas_ids = [
        "https://smartproductionlab.aau.dk/aas/aauFillingLine"
    ]

    # Test AAS connection
    client = test_aas_connection()

    # Test product AAS structure
    bill_of_processes = test_product_aas_structure(client, product_aas_id)

    # Test BillOfProcesses parsing
    process_steps, requirements = test_bill_of_processes_parsing(
        client, product_aas_id)

    # Test resource capability extraction
    resources_with_caps = test_resource_capabilities(client, resource_aas_ids)

    # Test capability matching
    result = test_capability_matching(client, product_aas_id, resource_aas_ids)
    if result:
        matching_result, product_config = result

        # Test BT generation
        bt_xml = test_bt_generation(matching_result, product_config)

        # Test Process AAS generation
        process_config = test_process_aas_generation(
            matching_result, product_config, requirements or {})

    print("\n" + "=" * 60)
    print("All Tests Completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
