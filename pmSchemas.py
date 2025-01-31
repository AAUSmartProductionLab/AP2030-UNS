import json
from jsonschema import validate
from jsonschema.exceptions import ValidationError


def load_schema(schema_file):
    with open(schema_file, 'r') as file:
        return json.load(file)


connectionRequestSchema = load_schema('connection.schema.json')

request = {}
request["address"] = "127.0.0.1"
request["target_state"] = "connected"

try:
    validate(instance=request, schema=connectionRequestSchema)
    print("Request is valid")
    json_string = json.dumps(request)
    print(json_string)
except ValidationError as e:
    print("Validation error:", e)
