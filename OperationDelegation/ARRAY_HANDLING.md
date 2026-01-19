# Array Handling in AAS Operations

## Problem

JSON schemas (like `moveToPosition.schema.json`) contain array fields such as:

```json
"Position": {
    "type": "array",
    "prefixItems": [
        { "type": "number", "description": "X position" },
        { "type": "number", "description": "Y position" },
        { "type": "number", "description": "Theta (rotation)" }
    ]
}
```

However, **XML Schema (xs:) does not have native array types**. AAS Operations only support simple datatypes:
- `xs:string`
- `xs:int` / `xs:integer`
- `xs:double` / `xs:float` / `xs:decimal`
- `xs:boolean`

Mapping an array to a single `xs:string` field causes it to be evaluated as a string instead of an array, breaking MQTT communication.

## Solution

**Split array fields into separate input variables** in the AAS Operation definition, then configure the array mapping in `topics.json`.

### Step 1: Define Individual Fields in AAS

```json
{
  "inputVariables": [
    {
      "value": {
        "idShort": "X",
        "description": [{"language": "en", "text": "Target X position in mm"}],
        "modelType": "Property",
        "valueType": "xs:double"
      }
    },
    {
      "value": {
        "idShort": "Y",
        "description": [{"language": "en", "text": "Target Y position in mm"}],
        "modelType": "Property",
        "valueType": "xs:double"
      }
    },
    {
      "value": {
        "idShort": "Theta",
        "description": [{"language": "en", "text": "Target rotation angle"}],
        "modelType": "Property",
        "valueType": "xs:double"
      }
    }
  ]
}
```

### Step 2: Configure Array Mapping in topics.json

Add the `array_mappings` configuration to specify how individual fields combine into arrays:

```json
{
  "planarTableShuttle1AAS": {
    "base_topic": "NN/Nybrovej/InnoLab/Planar/Xbot1",
    "submodel_id": "https://smartproductionlab.aau.dk/submodels/instances/planarTableShuttle1AAS/Skills",
    "skills": {
      "MoveToPosition": {
        "command_topic": "NN/Nybrovej/InnoLab/Planar/Xbot1/CMD/XYMotion",
        "response_topic": "NN/Nybrovej/InnoLab/Planar/Xbot1/DATA/XYMotion",
        "array_mappings": {
          "Position": ["X", "Y", "Theta"]
        }
      }
    }
  }
}
```

The `array_mappings` object maps MQTT array names to their AAS field components:
- **Key**: MQTT field name (e.g., `"Position"`)
- **Value**: Array of AAS field names in order (e.g., `["X", "Y", "Theta"]`)

### Automatic Transformation

The Operation Delegation Service automatically handles the transformation:

#### Input (AAS → MQTT)
Individual fields are combined into arrays based on configuration:
- AAS: `X=100, Y=200, Theta=0` 
- MQTT: `Position: [100, 200, 0]`

#### Output (MQTT → AAS)
Arrays are unpacked into individual fields:
- MQTT: `Position: [100, 200, 0]`
- AAS: `X=100, Y=200, Theta=0`

### Benefits

1. ✅ **Proper UI rendering** - BaSyx dashboard shows individual form fields
2. ✅ **Type safety** - Each field has proper validation (`xs:double`)
3. ✅ **Better UX** - Users enter values in separate labeled fields
4. ✅ **Fully configurable** - No hardcoded field names
5. ✅ **Automatic conversion** - Operation service handles array transformation

## Configuration Examples

### Single Array Mapping
```json
"array_mappings": {
  "Position": ["X", "Y", "Theta"]
}
```

### Multiple Arrays
```json
"array_mappings": {
  "Position": ["X", "Y", "Theta"],
  "Velocity": ["VX", "VY"],
  "RGB": ["Red", "Green", "Blue"]
}
```

### Partial Arrays (Optional Fields)
If a field is optional and not provided, it's simply omitted from the array:
- AAS: `X=100, Y=200` (no Theta)
- MQTT: `Position: [100, 200]`

## Implementation Details

See [`operation_delegation_service.py`](operation_delegation_service.py):

- `_build_command_message()` - Converts individual AAS properties to MQTT arrays
- `_build_response_variables()` - Unpacks MQTT arrays to individual AAS properties
- `invoke_operation()` - Passes array_mappings from topics.json configuration

## Other Schemas with Arrays

Apply the same pattern to these schemas by adding appropriate array_mappings:

- `moveCommand.json` - Position array
- `position.schema.json` - Position array  
- `planarStations.schema.json` - Multiple arrays (Stations, Limits)
- `planningCommand.schema.json` - Task array
- `stationOccupation.schema.json` - Occupation array
- `stationState.schema.json` - State array
