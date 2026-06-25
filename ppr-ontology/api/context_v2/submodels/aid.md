# Submodel Template: AID (Asset Interfaces Description)

- **idShort**: `AID`
- **Submodel ID pattern**: `{base_url}/submodels/instances/{systemId}/AID`
- **semanticId**: `https://admin-shell.io/idta/AssetInterfacesDescription/1/0/Submodel` (ExternalReference)
- **kind**: `Instance`
- **administration**: `{"version": "1", "revision": "1"}`

## Purpose

Describes the communication interfaces of the resource using the W3C Web of Things (WoT) Thing Description structure. Each interface (MQTT, HTTP, MODBUS) is a SubmodelElementCollection.

## DEPENDENCY RULES (Critical)

- AID is required if Skills, OperationalData, or Parameters are present.
- AID must have at least one Interface (ResourceInterface) — SHACL violation if empty.
- Each interface must contain an `InteractionMetadata` SMC with at least one affordance (property, action, or event).
- Each Skill in the Skills submodel must be represented as an Action affordance in the AID.

## Protocol Supplemental Semantic IDs

| Protocol | supplementalSemanticIds values |
|---|---|
| MQTT | `["https://www.w3.org/2019/wot/td/v1/binding/mqtt", "https://www.w3.org/2019/wot/td/v1"]` |
| HTTP | `["https://www.w3.org/2019/wot/td/v1/binding/http", "https://www.w3.org/2019/wot/td/v1"]` |
| MODBUS | `["https://www.w3.org/2019/wot/td/v1/binding/modbus", "https://www.w3.org/2019/wot/td/v1"]` |

## Interface Structure

Each Interface SMC:
- `idShort`: interface name (e.g. `InterfaceMQTT`, `InterfaceHTTP`)
- `semanticId`: `https://admin-shell.io/idta/AssetInterfacesDescription/1/0/Interface`
- `supplementalSemanticIds`: protocol-specific (see table above)
- `value`: array containing:
  1. `title` Property (optional)
  2. `EndpointMetadata` SMC — base URL and content type
  3. `InteractionMetadata` SMC — properties, actions, events

## InteractionMetadata Structure

```json
{
  "modelType": "SubmodelElementCollection",
  "idShort": "InteractionMetadata",
  "semanticId": {"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": "https://admin-shell.io/idta/AssetInterfacesDescription/1/0/InteractionMetadata"}]},
  "supplementalSemanticIds": [{"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": "https://www.w3.org/2019/wot/td#InteractionAffordance"}]}],
  "value": [
    {
      "modelType": "SubmodelElementCollection",
      "idShort": "properties",
      "semanticId": {"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": "https://www.w3.org/2019/wot/td#PropertyAffordance"}]},
      "value": [ ... property SMCs ... ]
    },
    {
      "modelType": "SubmodelElementCollection",
      "idShort": "actions",
      "semanticId": {"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": "https://www.w3.org/2019/wot/td#ActionAffordance"}]},
      "value": [ ... action SMCs ... ]
    }
  ]
}
```

## Property Affordance SMC

```json
{
  "modelType": "SubmodelElementCollection",
  "idShort": "{propertyKey}",
  "value": [
    {"modelType": "Property", "idShort": "Key", "valueType": "xs:string", "value": "{propertyKey}"},
    {"modelType": "Property", "idShort": "Title", "valueType": "xs:string", "value": "Human-readable title"},
    {
      "modelType": "SubmodelElementCollection",
      "idShort": "Forms",
      "value": [
        {"modelType": "Property", "idShort": "href", "valueType": "xs:string", "value": "device/topic/path"},
        {"modelType": "Property", "idShort": "op", "valueType": "xs:string", "value": "observeproperty"},
        {"modelType": "Property", "idShort": "mqv_retain", "valueType": "xs:string", "value": "false"}
      ]
    }
  ]
}
```

## Action Affordance SMC (one per Skill)

```json
{
  "modelType": "SubmodelElementCollection",
  "idShort": "{skillName}",
  "value": [
    {"modelType": "Property", "idShort": "Key", "valueType": "xs:string", "value": "{skillName}"},
    {"modelType": "Property", "idShort": "Title", "valueType": "xs:string", "value": "Human-readable title"},
    {"modelType": "Property", "idShort": "Synchronous", "valueType": "xs:boolean", "value": "true"},
    {
      "modelType": "SubmodelElementCollection",
      "idShort": "Forms",
      "value": [
        {"modelType": "Property", "idShort": "href", "valueType": "xs:string", "value": "device/skills/skillname"},
        {"modelType": "Property", "idShort": "op", "valueType": "xs:string", "value": "invokeaction"},
        {"modelType": "Property", "idShort": "contentType", "valueType": "xs:string", "value": "application/json"}
      ]
    }
  ]
}
```

## MQTT-Specific Forms Fields

| idShort | valueType | Description |
|---|---|---|
| `href` | `xs:string` | MQTT topic (e.g. `"device/sensors/temperature"`) |
| `op` | `xs:string` | `"observeproperty"` for subscribe, `"invokeaction"` for publish |
| `mqv_retain` | `xs:string` | `"true"` or `"false"` |
| `mqv_controlPacket` | `xs:string` | MQTT packet type |
| `mqv_qos` | `xs:string` | `"0"`, `"1"`, or `"2"` |

## JSON Template (MQTT interface)

```json
{
  "modelType": "Submodel",
  "id": "{base_url}/submodels/instances/{systemId}/AID",
  "idShort": "AID",
  "kind": "Instance",
  "semanticId": {
    "type": "ExternalReference",
    "keys": [{"type": "GlobalReference", "value": "https://admin-shell.io/idta/AssetInterfacesDescription/1/0/Submodel"}]
  },
  "administration": {"version": "1", "revision": "1"},
  "submodelElements": [
    {
      "modelType": "SubmodelElementCollection",
      "idShort": "InterfaceMQTT",
      "semanticId": {
        "type": "ExternalReference",
        "keys": [{"type": "GlobalReference", "value": "https://admin-shell.io/idta/AssetInterfacesDescription/1/0/Interface"}]
      },
      "supplementalSemanticIds": [
        {"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": "https://www.w3.org/2019/wot/td/v1/binding/mqtt"}]},
        {"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": "https://www.w3.org/2019/wot/td/v1"}]}
      ],
      "value": [
        {"modelType": "Property", "idShort": "title", "valueType": "xs:string", "value": "MQTT Interface"},
        {
          "modelType": "SubmodelElementCollection",
          "idShort": "EndpointMetadata",
          "value": [
            {"modelType": "Property", "idShort": "base", "valueType": "xs:anyURI", "value": "mqtt://broker.example.com"},
            {"modelType": "Property", "idShort": "contentType", "valueType": "xs:string", "value": "application/json"}
          ]
        },
        {
          "modelType": "SubmodelElementCollection",
          "idShort": "InteractionMetadata",
          "semanticId": {"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": "https://admin-shell.io/idta/AssetInterfacesDescription/1/0/InteractionMetadata"}]},
          "supplementalSemanticIds": [{"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": "https://www.w3.org/2019/wot/td#InteractionAffordance"}]}],
          "value": [
            {
              "modelType": "SubmodelElementCollection",
              "idShort": "properties",
              "semanticId": {"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": "https://www.w3.org/2019/wot/td#PropertyAffordance"}]},
              "value": []
            },
            {
              "modelType": "SubmodelElementCollection",
              "idShort": "actions",
              "semanticId": {"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": "https://www.w3.org/2019/wot/td#ActionAffordance"}]},
              "value": []
            }
          ]
        }
      ]
    }
  ]
}
```

## Notes

- If the spec sheet mentions MQTT: use MQTT protocol with the broker URL as `base`.
- If the spec sheet mentions REST/HTTP: use HTTP protocol.
- Add one Action entry per Skill defined in the Skills submodel.
- Add Property entries for each runtime variable (from OperationalData) if interface details are available.
- Use placeholder MQTT topics like `device/skills/{skillName}` or `device/sensors/{varName}` if not specified.
