#!/usr/bin/env python3
"""
Test script for the planning package.

This script tests the planning modules without requiring MQTT or AAS server connectivity.
It uses mock data to validate the capability matching, BT generation, and process AAS generation.
"""

import os
import sys
import json
from dataclasses import asdict

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from planning.capability_matcher import CapabilityMatcher, ProcessStep
from planning.bt_generator import BTGenerator, BTGeneratorConfig
from planning.process_aas_generator import ProcessAASGenerator


def test_capability_matching():
    """Test capability matching with mock data"""
    print("=" * 60)
    print("Testing Capability Matching")
    print("=" * 60)
    
    # Mock process steps from product BillOfProcesses
    process_steps = [
        ProcessStep(name="Loading", step=1, 
                    semantic_id="https://smartproductionlab.aau.dk/Capability/Loading",
                    description="Load container onto shuttle"),
        ProcessStep(name="Dispensing", step=2,
                    semantic_id="https://smartproductionlab.aau.dk/Capability/Dispensing",
                    description="Dispense product"),
        ProcessStep(name="Stoppering", step=3,
                    semantic_id="https://smartproductionlab.aau.dk/Capability/Stoppering",
                    description="Insert stopper"),
        ProcessStep(name="Inspection", step=4,
                    semantic_id="https://smartproductionlab.aau.dk/Capability/QualityControl",
                    description="Visual inspection"),
        ProcessStep(name="Unloading", step=5,
                    semantic_id="https://smartproductionlab.aau.dk/Capability/Unloading",
                    description="Unload finished product"),
    ]
    
    # Mock available resources with capabilities
    available_resources = [
        "https://smartproductionlab.aau.dk/aas/aauFillingLine"
    ]
    
    # Create matcher (with None aas_client since we're using mock data)
    matcher = CapabilityMatcher(aas_client=None)
    
    # Perform matching
    result = matcher.match_capabilities(process_steps, available_resources)
    
    print(f"\nMatching Results:")
    print(f"  Total process steps: {len(process_steps)}")
    print(f"  Matched steps: {len(process_steps) - len(result.unmatched_steps)}")
    print(f"  Unmatched steps: {len(result.unmatched_steps)}")
    print(f"  Movers found: {len(result.movers)}")
    print(f"  Parallelism factor: {result.parallelism_factor}")
    print(f"  Is complete: {result.is_complete}")
    
    print("\nProcess Matches:")
    for match in result.process_matches:
        status = "✓" if match.is_matched else "✗"
        resource = match.primary_resource.resource_name if match.primary_resource else "None"
        print(f"  {status} {match.process_step.name} -> {resource}")
    
    print("\nMovers:")
    for mover in result.movers:
        print(f"  - {mover.name} ({mover.aas_id})")
    
    return result


def test_bt_generation(matching_result):
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
    
    # Mock product info
    product_info = {
        "ProductInformation": {
            "ProductName": "HgH"
        },
        "BatchInformation": {
            "Quantity": 40000
        }
    }
    
    # Generate BT
    bt_xml = generator.generate_production_bt(
        matching_result,
        product_info,
        planar_table_id="https://smartproductionlab.aau.dk/aas/planarTable"
    )
    
    print("\nGenerated Behavior Tree (first 2000 chars):")
    print("-" * 40)
    print(bt_xml[:2000])
    if len(bt_xml) > 2000:
        print(f"\n... ({len(bt_xml) - 2000} more characters)")
    
    # Get blackboard parameters
    params = generator.get_blackboard_parameters(
        matching_result,
        planar_table_id="https://smartproductionlab.aau.dk/aas/planarTable"
    )
    
    print("\nBlackboard Parameters:")
    for key, value in params.items():
        print(f"  {key}: {value}")
    
    return bt_xml


def test_process_aas_generation(matching_result):
    """Test Process AAS configuration generation"""
    print("\n" + "=" * 60)
    print("Testing Process AAS Generation")
    print("=" * 60)
    
    generator = ProcessAASGenerator()
    
    # Mock product info
    product_info = {
        "id": "https://smartproductionlab.aau.dk/aas/HgHAAS",
        "idShort": "HgHAAS",
        "ProductInformation": {
            "ProductName": "Human Growth Hormone"
        },
        "BatchInformation": {
            "OrderNumber": "ORD-2026-001",
            "Quantity": 40000,
            "Unit": "units"
        }
    }
    
    # Mock requirements
    requirements = {
        "environmental": {
            "Temperature": {"value": 18, "unit": "°C"}
        },
        "in_process_control": {
            "Weighing": {
                "semantic_id": "https://smartproductionlab.aau.dk/Capability/Weighing",
                "applies_to": "Dispensing",
                "rate": 100,
                "unit": "%"
            }
        },
        "quality_control": {
            "VisualInspection": {
                "semantic_id": "https://smartproductionlab.aau.dk/Capability/QualityControl",
                "rate": 85,
                "unit": "%"
            }
        }
    }
    
    # Generate config
    config = generator.generate_config(
        matching_result,
        "https://smartproductionlab.aau.dk/aas/HgHAAS",
        product_info,
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


def test_extract_from_yaml():
    """Test extraction of process steps from YAML config"""
    print("\n" + "=" * 60)
    print("Testing YAML Config Extraction")
    print("=" * 60)
    
    # Load the HgH product config
    import yaml
    
    # Try multiple possible paths
    possible_paths = [
        "../AASDescriptions/Product/configs/HgH.yaml",
        "../../AASDescriptions/Product/configs/HgH.yaml",
        os.path.join(os.path.dirname(__file__), "..", "..", "AASDescriptions", "Product", "configs", "HgH.yaml"),
    ]
    
    config_path = None
    for path in possible_paths:
        if os.path.exists(path):
            config_path = path
            break
    
    if not config_path:
        print(f"  Config file not found in any of: {possible_paths}")
        return None, None
    
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        # Get the product config
        product_key = list(config.keys())[0]
        product_config = config[product_key]
        
        # Create matcher and extract
        matcher = CapabilityMatcher(aas_client=None)
        steps = matcher.extract_process_steps(product_config)
        requirements = matcher.extract_requirements(product_config)
        
        print(f"\nExtracted from {config_path}:")
        print(f"\nProcess Steps ({len(steps)}):")
        for step in steps:
            print(f"  {step.step}. {step.name}")
            print(f"     Semantic ID: {step.semantic_id}")
            print(f"     Duration: {step.estimated_duration}s")
        
        print(f"\nRequirements:")
        print(f"  Environmental: {list(requirements['environmental'].keys())}")
        print(f"  In-Process Control: {list(requirements['in_process_control'].keys())}")
        print(f"  Quality Control: {list(requirements['quality_control'].keys())}")
        
        return steps, requirements
        
    except Exception as e:
        print(f"  Error loading config: {e}")
        return None, None


def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("Production Planning Package Test Suite")
    print("=" * 60)
    
    # Test capability matching
    matching_result = test_capability_matching()
    
    # Test BT generation
    bt_xml = test_bt_generation(matching_result)
    
    # Test Process AAS generation
    process_config = test_process_aas_generation(matching_result)
    
    # Test YAML extraction
    test_extract_from_yaml()
    
    print("\n" + "=" * 60)
    print("All Tests Completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
