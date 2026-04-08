# Submodel Template: DigitalNameplate

- **idShort**: `DigitalNameplate`
- **Submodel ID pattern**: `{base_url}/submodels/instances/{systemId}/DigitalNameplate`
- **semanticId**: `https://admin-shell.io/idta/nameplate/3/0/Nameplate` (ExternalReference)
- **kind**: `Instance`
- **administration**: `{"version": "1", "revision": "1"}`

## Required Fields (SHACL violations if missing)

| idShort | modelType | valueType | Notes |
|---|---|---|---|
| `ManufacturerName` | `MultiLanguageProperty` | — | value: `[{"language": "en", "text": "..."}]` — MANDATORY |
| `SerialNumber` | `Property` | `xs:string` | MANDATORY |

## Optional Fields

| idShort | modelType | valueType | Format constraint |
|---|---|---|---|
| `ManufacturerProductDesignation` | `MultiLanguageProperty` | — | Multi-language |
| `ManufacturerProductFamily` | `MultiLanguageProperty` | — | Multi-language |
| `URIOfTheProduct` | `Property` | `xs:string` | Product URI |
| `ManufacturerArticleNumber` | `Property` | `xs:string` | — |
| `BatchNumber` | `Property` | `xs:string` | — |
| `YearOfConstruction` | `Property` | `xs:string` | **Exactly 4 digits: `YYYY`** |
| `DateOfManufacture` | `Property` | `xs:string` | **Format: `YYYY-MM-DD`** |
| `HardwareVersion` | `Property` | `xs:string` | — |
| `SoftwareVersion` | `Property` | `xs:string` | — |
| `CountryOfOrigin` | `Property` | `xs:string` | ISO 3166-1 alpha-2 |

## JSON Template

```json
{
  "modelType": "Submodel",
  "id": "{base_url}/submodels/instances/{systemId}/DigitalNameplate",
  "idShort": "DigitalNameplate",
  "kind": "Instance",
  "semanticId": {
    "type": "ExternalReference",
    "keys": [{"type": "GlobalReference", "value": "https://admin-shell.io/idta/nameplate/3/0/Nameplate"}]
  },
  "administration": {"version": "1", "revision": "1"},
  "submodelElements": [
    {
      "modelType": "MultiLanguageProperty",
      "idShort": "ManufacturerName",
      "value": [{"language": "en", "text": "<manufacturer name from spec sheet>"}]
    },
    {
      "modelType": "MultiLanguageProperty",
      "idShort": "ManufacturerProductDesignation",
      "value": [{"language": "en", "text": "<product designation>"}]
    },
    {
      "modelType": "Property",
      "idShort": "SerialNumber",
      "valueType": "xs:string",
      "value": "<serial number>"
    },
    {
      "modelType": "Property",
      "idShort": "YearOfConstruction",
      "valueType": "xs:string",
      "value": "2024"
    }
  ]
}
```

## Notes

- Extract manufacturer name, serial/part numbers, product family, version strings from the spec sheet.
- If only a model number is available and no explicit serial number, use the model number as
  `SerialNumber` (it is a mandatory field).
- `YearOfConstruction` must be exactly 4 digits — never include month or day.
- `DateOfManufacture` must be `YYYY-MM-DD` — only include if a full date is known.
