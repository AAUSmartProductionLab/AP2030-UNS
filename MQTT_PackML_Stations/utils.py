import json


def load_schema(schema_file):
    if schema_file == None:
        return None
    with open(schema_file, 'r') as file:
        return json.load(file)
