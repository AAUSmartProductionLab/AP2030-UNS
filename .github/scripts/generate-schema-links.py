#!/usr/bin/env python3
"""
Script to automatically generate schema and behavior tree links for the documentation page.
This script scans the docs/schemas directory and docs/bt_description directory
and generates markdown links for all schema and XML files.
"""

import os
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List

def get_schema_title(schema_path: Path) -> str:
    """Extract the title from a JSON schema file, or use filename as fallback."""
    try:
        with open(schema_path, 'r') as f:
            schema = json.load(f)
            if 'title' in schema:
                return schema['title']
            elif '$id' in schema:
                # Use $id as a fallback
                return schema['$id']
    except (json.JSONDecodeError, Exception):
        pass
    
    # Fallback to filename
    return schema_path.stem.replace('_', ' ').replace('.schema', '').title()

def get_schema_description(schema_path: Path) -> str:
    """Extract the description from a JSON schema file."""
    try:
        with open(schema_path, 'r') as f:
            schema = json.load(f)
            if 'description' in schema:
                return schema['description']
    except (json.JSONDecodeError, Exception):
        pass
    return None

def get_bt_title(bt_path: Path) -> tuple[str, bool]:
    """Extract a title from a BT XML file, or use filename as fallback.
    
    Returns:
        tuple: (title, was_extracted) where was_extracted indicates if the title
               was found in the XML (True) or is a fallback (False)
    """
    try:
        tree = ET.parse(bt_path)
        root = tree.getroot()
        # Try to get the first BehaviorTree ID
        bt_node = root.find('.//BehaviorTree')
        if bt_node is not None and 'ID' in bt_node.attrib:
            return bt_node.attrib['ID'], True
    except (ET.ParseError, Exception):
        pass
    
    # Fallback to filename
    return bt_path.stem.replace('_', ' ').title(), False

def get_bt_description(bt_path: Path) -> str:
    """Extract description from BT XML file if available."""
    try:
        tree = ET.parse(bt_path)
        root = tree.getroot()
        # Look for a description or comment node
        comment = root.find('.//description')
        if comment is not None:
            return comment.text
    except (ET.ParseError, Exception):
        pass
    return None

def scan_schemas(schemas_dir: Path, base_path: str = '') -> Dict[str, List[Dict]]:
    """Scan the schemas directory and organize schemas by category.
    
    Args:
        schemas_dir: The directory to scan for JSON schemas
        base_path: The base path to prepend to relative paths (e.g., 'AASDescriptions', 'MQTTSchemas')
    """
    categories = {}
    
    for schema_file in schemas_dir.rglob('*.json'):
        # Get relative path from schemas directory
        rel_path = schema_file.relative_to(schemas_dir)
        
        # Build full path including base_path
        if base_path:
            full_path = f"{base_path}/{rel_path.as_posix()}"
        else:
            full_path = rel_path.as_posix()
        
        # Determine category based on directory structure
        parts = rel_path.parts
        
        if base_path == 'AASDescriptions':
            # AASDescriptions subfolder structure: Process/, Product/, Resource/
            if len(parts) > 1:
                category = f"AAS {parts[0]} Descriptions"
            else:
                category = 'AAS Descriptions'
        elif base_path == 'MQTTSchemas':
            # MQTT Schemas
            category = 'MQTT Schemas'
        elif len(parts) > 1:
            # Other subdirectories
            category = parts[0].replace('_', ' ').title()
        else:
            # Root-level schemas (fallback)
            category = 'Other'
        
        if category not in categories:
            categories[category] = []
        
        title = get_schema_title(schema_file)
        description = get_schema_description(schema_file)
        
        categories[category].append({
            'title': title,
            'filename': schema_file.name,
            'path': full_path,
            'description': description
        })
    
    # Sort schemas within each category
    for category in categories:
        categories[category].sort(key=lambda x: x['filename'])
    
    return categories

def scan_bt_xmls(bt_dir: Path) -> List[Dict]:
    """Scan the BT description directory for XML files."""
    bt_files = []
    
    if not bt_dir.exists():
        return bt_files
    
    for xml_file in bt_dir.glob('*.xml'):
        title, was_extracted = get_bt_title(xml_file)
        description = get_bt_description(xml_file)
        
        bt_files.append({
            'title': title,
            'filename': xml_file.name,
            'description': description,
            'has_tree_id': was_extracted
        })
    
    # Sort by filename
    bt_files.sort(key=lambda x: x['filename'])
    
    return bt_files

def generate_markdown_schemas(categories: Dict[str, List[Dict]]) -> str:
    """Generate markdown content for the schema links."""
    lines = []
    
    # Define category order for better organization
    category_order = [
        'AAS Process Descriptions',
        'AAS Product Descriptions', 
        'AAS Resource Descriptions',
        'MQTT Schemas'
    ]
    
    # First, add ordered categories
    for category in category_order:
        if category in categories:
            schemas = categories[category]
            lines.append(f"### {category}\n")
            
            for schema in schemas:
                # Create link
                github_pages_url = f"https://aausmartproductionlab.github.io/AP2030-UNS/{schema['path']}"
                raw_url = f"https://raw.githubusercontent.com/AAUSmartProductionLab/AP2030-UNS/main/{schema['path']}"
                
                lines.append(f"- **[{schema['filename']}]({schema['path']})**")
                if schema['description']:
                    lines.append(f"  - {schema['description']}")
                lines.append(f"  - [View on GitHub Pages]({github_pages_url})")
                lines.append(f"  - [Raw]({raw_url})")
            
            lines.append("")  # Empty line between categories
    
    # Then add any remaining categories not in the predefined order
    for category, schemas in sorted(categories.items()):
        if category not in category_order:
            lines.append(f"### {category}\n")
            
            for schema in schemas:
                github_pages_url = f"https://aausmartproductionlab.github.io/AP2030-UNS/{schema['path']}"
                raw_url = f"https://raw.githubusercontent.com/AAUSmartProductionLab/AP2030-UNS/main/{schema['path']}"
                
                lines.append(f"- **[{schema['filename']}]({schema['path']})**")
                if schema['description']:
                    lines.append(f"  - {schema['description']}")
                lines.append(f"  - [View on GitHub Pages]({github_pages_url})")
                lines.append(f"  - [Raw]({raw_url})")
            
            lines.append("")  # Empty line between categories
    
    return '\n'.join(lines)

def generate_markdown_bts(bt_files: List[Dict]) -> str:
    """Generate markdown content for the BT XML links."""
    lines = []
    
    for bt in bt_files:
        # Create links
        github_pages_url = f"https://aausmartproductionlab.github.io/AP2030-UNS/BTDescriptions/{bt['filename']}"
        raw_url = f"https://raw.githubusercontent.com/AAUSmartProductionLab/AP2030-UNS/main/BTDescriptions/{bt['filename']}"
        
        lines.append(f"- **[{bt['filename']}](BTDescriptions/{bt['filename']})**")
        if bt['description']:
            lines.append(f"  - {bt['description']}")
        if bt['has_tree_id']:
            lines.append(f"  - Tree ID: `{bt['title']}`")
        lines.append(f"  - [View on GitHub Pages]({github_pages_url})")
        lines.append(f"  - [Raw]({raw_url})")
        lines.append("")  # Empty line between files
    
    return '\n'.join(lines)

def update_index_md(docs_dir: Path, schema_content: str, bt_content: str):
    """Update the index.md file with the generated schema and BT links."""
    index_path = docs_dir / 'index.md'
    
    # Read the current index.md
    with open(index_path, 'r') as f:
        content = f.read()
    
    # Define markers for the auto-generated sections
    schema_start = "<!-- AUTO-GENERATED-SCHEMAS-START -->"
    schema_end = "<!-- AUTO-GENERATED-SCHEMAS-END -->"
    bt_start = "<!-- AUTO-GENERATED-BT-START -->"
    bt_end = "<!-- AUTO-GENERATED-BT-END -->"
    
    # Update schemas section
    if schema_start in content and schema_end in content:
        start_idx = content.find(schema_start) + len(schema_start)
        end_idx = content.find(schema_end)
        content = (
            content[:start_idx] + 
            "\n" + schema_content + "\n" +
            content[end_idx:]
        )
    else:
        # Append to the end of the file
        content += f"\n\n{schema_start}\n{schema_content}\n{schema_end}\n"
    
    # Update BT section
    if bt_start in content and bt_end in content:
        start_idx = content.find(bt_start) + len(bt_start)
        end_idx = content.find(bt_end)
        content = (
            content[:start_idx] + 
            "\n" + bt_content + "\n" +
            content[end_idx:]
        )
    else:
        # Append to the end of the file
        content += f"\n\n{bt_start}\n{bt_content}\n{bt_end}\n"
    
    # Write the updated content
    with open(index_path, 'w') as f:
        f.write(content)

def main():
    # Get the docs directory
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent.parent
    docs_dir = repo_root / 'docs'
    aas_dir = docs_dir / 'AASDescriptions'
    mqtt_dir = docs_dir / 'MQTTSchemas'
    bt_dir = docs_dir / 'BTDescriptions'
    
    # Scan all three directories
    categories = {}
    
    if aas_dir.exists():
        print(f"Scanning AAS descriptions in {aas_dir}...")
        aas_categories = scan_schemas(aas_dir, base_path='AASDescriptions')
        categories.update(aas_categories)
    
    if mqtt_dir.exists():
        print(f"Scanning MQTT schemas in {mqtt_dir}...")
        mqtt_categories = scan_schemas(mqtt_dir, base_path='MQTTSchemas')
        categories.update(mqtt_categories)
    
    print(f"Found {sum(len(s) for s in categories.values())} schemas in {len(categories)} categories")
    
    print(f"Scanning BT XMLs in {bt_dir}...")
    bt_files = scan_bt_xmls(bt_dir)
    
    print(f"Found {len(bt_files)} behavior tree XML files")
    
    print("Generating markdown content...")
    schema_content = generate_markdown_schemas(categories)
    bt_content = generate_markdown_bts(bt_files)
    
    print("Updating index.md...")
    update_index_md(docs_dir, schema_content, bt_content)
    
    print("✓ Schema and BT links generated successfully!")
    return 0

if __name__ == '__main__':
    exit(main())
