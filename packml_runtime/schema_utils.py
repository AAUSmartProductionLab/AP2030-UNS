import json
import os
from jsonschema import RefResolver
def load_schema(schema_path):
    if schema_path == None:
        return None
    
    try:
        with open(schema_path, 'r') as f:
            schema = json.load(f)
        
        # Create base URI for schema resolution - points to schemas directory
        schema_dir = os.path.abspath(os.path.dirname(schema_path))
        resolver = RefResolver(f'file://{schema_dir}/', schema)
        
        return schema, resolver
    except Exception as e:
        print(f"Error loading schema {schema_path}: {e}")
        return None, None
