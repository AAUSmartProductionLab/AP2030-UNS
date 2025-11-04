#!/usr/bin/env python3
"""
Script to automatically generate schema links for the documentation page.
This script scans the docs/schemas directory and generates markdown links
for all schema files.
"""

import os
import json
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

def scan_schemas(schemas_dir: Path) -> Dict[str, List[Dict]]:
    """Scan the schemas directory and organize schemas by category."""
    categories = {}
    
    for schema_file in schemas_dir.rglob('*.json'):
        # Get relative path from schemas directory
        rel_path = schema_file.relative_to(schemas_dir)
        
        # Determine category based on directory structure
        if len(rel_path.parts) > 1:
            category = rel_path.parts[0]
        else:
            # Categorize root-level schemas by name pattern
            filename = schema_file.stem.lower()
            if 'command' in filename:
                category = 'Command'
            elif 'amr' in filename or 'arcl' in filename:
                category = 'AMR (Mobile Robot)'
            elif any(x in filename for x in ['data', 'state', 'weight', 'image']):
                category = 'Data & State'
            elif any(x in filename for x in ['config', 'order', 'product']):
                category = 'Configuration'
            elif any(x in filename for x in ['station', 'planar', 'move']):
                category = 'Station & Movement'
            else:
                category = 'Other'
        
        # Format category name
        if category == 'ResourceDescription':
            category = 'AAS Resource Descriptions'
        
        if category not in categories:
            categories[category] = []
        
        title = get_schema_title(schema_file)
        description = get_schema_description(schema_file)
        
        categories[category].append({
            'title': title,
            'filename': schema_file.name,
            'path': str(rel_path.as_posix()),
            'description': description
        })
    
    # Sort schemas within each category
    for category in categories:
        categories[category].sort(key=lambda x: x['filename'])
    
    return categories

def generate_markdown(categories: Dict[str, List[Dict]]) -> str:
    """Generate markdown content for the schema links."""
    lines = []
    
    # Sort categories for consistent output
    sorted_categories = sorted(categories.items())
    
    for category, schemas in sorted_categories:
        lines.append(f"### {category}\n")
        
        for schema in schemas:
            # Create link
            github_pages_url = f"https://aausmartproductionlab.github.io/AP2030-UNS/schemas/{schema['path']}"
            raw_url = f"https://raw.githubusercontent.com/AAUSmartProductionLab/AP2030-UNS/main/schemas/{schema['path']}"
            
            lines.append(f"- **[{schema['filename']}](schemas/{schema['path']})**")
            if schema['description']:
                lines.append(f"  - {schema['description']}")
            lines.append(f"  - [View on GitHub Pages]({github_pages_url})")
            lines.append(f"  - [Raw]({raw_url})")
        
        lines.append("")  # Empty line between categories
    
    return '\n'.join(lines)

def update_index_md(docs_dir: Path, schema_content: str):
    """Update the index.md file with the generated schema links."""
    index_path = docs_dir / 'index.md'
    
    # Read the current index.md
    with open(index_path, 'r') as f:
        content = f.read()
    
    # Define markers for the auto-generated section
    start_marker = "<!-- AUTO-GENERATED-SCHEMAS-START -->"
    end_marker = "<!-- AUTO-GENERATED-SCHEMAS-END -->"
    
    if start_marker in content and end_marker in content:
        # Replace the content between markers
        start_idx = content.find(start_marker) + len(start_marker)
        end_idx = content.find(end_marker)
        
        new_content = (
            content[:start_idx] + 
            "\n" + schema_content + "\n" +
            content[end_idx:]
        )
    else:
        # Append to the end of the file
        new_content = content + f"\n\n{start_marker}\n{schema_content}\n{end_marker}\n"
    
    # Write the updated content
    with open(index_path, 'w') as f:
        f.write(new_content)

def main():
    # Get the docs directory
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent.parent
    docs_dir = repo_root / 'docs'
    schemas_dir = docs_dir / 'schemas'
    
    if not schemas_dir.exists():
        print(f"Error: Schemas directory not found at {schemas_dir}")
        return 1
    
    print(f"Scanning schemas in {schemas_dir}...")
    categories = scan_schemas(schemas_dir)
    
    print(f"Found {sum(len(s) for s in categories.values())} schemas in {len(categories)} categories")
    
    print("Generating markdown content...")
    schema_content = generate_markdown(categories)
    
    print("Updating index.md...")
    update_index_md(docs_dir, schema_content)
    
    print("✓ Schema links generated successfully!")
    return 0

if __name__ == '__main__':
    exit(main())
