# AAS Array Handling Options

## Option 1: Separate Properties (Current Implementation ✓)

**Pros:**
- Simple and works with current BaSyx UI
- Clear field labels (X, Y, Theta)
- Easy validation per field
- Compatible with operation delegation service

**Cons:**
- Not semantically an array
- Requires special handling in delegation service

```json
"inputVariables": [
  {"value": {"idShort": "X", "valueType": "xs:double"}},
  {"value": {"idShort": "Y", "valueType": "xs:double"}},
  {"value": {"idShort": "Theta", "valueType": "xs:double"}}
]
```

## Option 2: SubmodelElementList (AAS Native Array)

**Pros:**
- Semantically correct - it IS an array
- Proper AAS metamodel structure
- Can have variable length

**Cons:**
- **BaSyx UI support unclear** - might not render well in operation forms
- More complex structure
- Operation variables typically expect flat Properties

```json
"inputVariables": [
  {
    "value": {
      "idShort": "Position",
      "modelType": "SubmodelElementList",
      "typeValueListElement": "Property",
      "valueTypeListElement": "xs:double",
      "value": [
        {"idShort": "0", "modelType": "Property", "valueType": "xs:double", "value": "100.0"},
        {"idShort": "1", "modelType": "Property", "valueType": "xs:double", "value": "200.0"},
        {"idShort": "2", "modelType": "Property", "valueType": "xs:double", "value": "0.0"}
      ]
    }
  }
]
```

## Option 3: Single String Property with Manual Parsing

**Pros:**
- Simple to define
- Single input field

**Cons:**
- No type safety
- String parsing required: `"[100, 200, 0]"` or `"100,200,0"`
- Poor UX - no validation
- Error-prone

```json
"inputVariables": [
  {
    "value": {
      "idShort": "Position",
      "valueType": "xs:string",
      "value": "[100.0, 200.0, 0.0]"
    }
  }
]
```

## Recommendation

**Use Option 1 (Separate Properties)** because:

1. ✅ Works reliably with BaSyx UI
2. ✅ Type-safe with proper validation
3. ✅ Good user experience
4. ✅ Already implemented in operation_delegation_service.py
5. ⚠️ SubmodelElementList support in Operation inputVariables is unclear/untested

## Testing SubmodelElementList

If you want to experiment with SubmodelElementList in operations, you would need to:

1. Update AAS definition to use SubmodelElementList
2. Test if BaSyx operation invocation UI can handle it
3. Update operation_delegation_service.py to extract values from the list structure
4. Check if BaSyx sends the list structure properly in POST requests

**Current status**: The separate properties approach is proven and working. SubmodelElementList might be more "correct" semantically, but practical BaSyx support is uncertain.
