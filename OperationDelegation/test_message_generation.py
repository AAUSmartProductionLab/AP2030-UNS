#!/usr/bin/env python3
"""
Test script to verify MQTT message generation from schemas.

Tests that MoveToPosition commands are correctly generated according to the schema.
"""

import json
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(__file__))

from schema_parser import SchemaParser, determine_field_mappings
from datetime import datetime, timezone


def test_move_to_position():
    """Test MoveToPosition message generation."""
    print("=" * 60)
    print("Testing MoveToPosition Message Generation")
    print("=" * 60)
    
    # Initialize parser
    parser = SchemaParser(local_schema_dir="../MQTTSchemas")
    
    # Parse the moveToPosition schema
    schema_url = "https://aausmartproductionlab.github.io/AP2030-UNS/MQTTSchemas/moveToPosition.schema.json"
    
    print(f"\n1. Parsing schema: {schema_url}")
    try:
        structure = parser.extract_message_structure(schema_url)
        print(f"   ✓ Schema parsed successfully")
        print(f"   Required fields: {structure['required_fields']}")
        print(f"   Field types: {json.dumps(structure['field_types'], indent=4)}")
        print(f"   Array fields: {json.dumps(structure['array_fields'], indent=4)}")
    except Exception as e:
        print(f"   ✗ Failed to parse schema: {e}")
        return False
    
    # Simulate AAS input variables (X, Y, TimeStamp, Velocity)
    # TimeStamp should come from AAS as xs:dateTime
    aas_fields = ['X', 'Y', 'TimeStamp', 'Velocity']
    print(f"\n2. AAS Input Fields: {aas_fields}")
    
    # Determine mappings
    print(f"\n3. Determining field mappings...")
    array_mappings, simple_mappings, unmapped = determine_field_mappings(aas_fields, structure)
    print(f"   Array mappings: {json.dumps(array_mappings, indent=4)}")
    print(f"   Simple mappings: {json.dumps(simple_mappings, indent=4)}")
    print(f"   Unmapped fields: {unmapped}")
    
    # Simulate building a command message
    print(f"\n4. Building command message...")
    field_values = {
        'X': 100.5,
        'Y': 200.3,
        'TimeStamp': datetime.now(timezone.utc).isoformat(),  # From AAS as xs:dateTime
        'Velocity': 50.0
    }
    
    command = {
        "Uuid": "test-uuid-1234"
    }
    
    # Add simple mapped fields (like TimeStamp) - simple_mappings is now {schema_field: {aas_field, type, format}}
    for schema_field, mapping_info in simple_mappings.items():
        aas_field = mapping_info["aas_field"]
        if aas_field in field_values:
            command[schema_field] = field_values[aas_field]
    
    # Pack arrays - ONLY include fields that map to schema
    packed_fields = set(m["aas_field"] for m in simple_mappings.values())
    if array_mappings:
        for parent_field, mappings in array_mappings.items():
            sorted_mappings = sorted(mappings, key=lambda m: m.get('index', 0))
            array_values = []
            
            for mapping in sorted_mappings:
                aas_field = mapping['aas_field']
                is_optional = mapping.get('optional', False)
                default_value = mapping.get('default')
                
                if aas_field in field_values:
                    array_values.append(field_values[aas_field])
                    packed_fields.add(aas_field)
                elif is_optional and default_value is not None:
                    array_values.append(default_value)
            
            command[parent_field] = array_values
    
    # DO NOT add unmapped fields - they are not in the schema!
    # This is strict schema compliance
    if unmapped:
        print(f"   ⚠ Dropping unmapped fields (not in schema): {unmapped}")
    
    print(f"\n5. Generated MQTT Message:")
    print(json.dumps(command, indent=2))
    
    # Verify against schema expectations
    print(f"\n6. Schema Compliance Check:")
    checks_passed = True
    
    if "Uuid" not in command:
        print(f"   ✗ Missing required field: Uuid")
        checks_passed = False
    else:
        print(f"   ✓ Uuid present: {command['Uuid']}")
    
    if "TimeStamp" not in command:
        print(f"   ✗ Missing required field: TimeStamp")
        checks_passed = False
    else:
        print(f"   ✓ TimeStamp present: {command['TimeStamp']}")
    
    if "Position" not in command:
        print(f"   ✗ Missing required field: Position")
        checks_passed = False
    elif not isinstance(command["Position"], list):
        print(f"   ✗ Position should be an array, got: {type(command['Position'])}")
        checks_passed = False
    elif len(command["Position"]) < 2:
        print(f"   ✗ Position array too short (min 2 items): {len(command['Position'])}")
        checks_passed = False
    else:
        print(f"   ✓ Position array: {command['Position']}")
    
    if "Velocity" not in command:
        print(f"   ✓ Velocity correctly excluded (not in schema)")
    else:
        print(f"   ✗ Velocity should not be in message (not in schema): {command['Velocity']}")
        checks_passed = False
    
    print(f"\n{'='*60}")
    if checks_passed:
        print("✓ ALL CHECKS PASSED - Message conforms to schema!")
    else:
        print("✗ SOME CHECKS FAILED - Message does not conform to schema")
    print(f"{'='*60}\n")
    
    return checks_passed


if __name__ == "__main__":
    success = test_move_to_position()
    sys.exit(0 if success else 1)
