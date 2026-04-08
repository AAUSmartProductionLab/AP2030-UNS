# ResourceAAS Generation Context — Preamble

You are generating an **Asset Administration Shell (AAS) JSON document** conforming to the AAS
Part 2 v3.1 specification and the ResourceAAS ontology (CSS/CASK/CSSx) used at Aalborg University's
Smart Production Lab.

## CRITICAL OUTPUT RULE

**Output ONLY a single valid JSON object — no prose, no markdown code fences, no explanations
before or after. The first character of your response MUST be `{`.**

---

## Top-Level JSON Envelope

The document MUST follow exactly this envelope structure:

```json
{
  "assetAdministrationShells": [ <one AAS shell object> ],
  "submodels": [ <array of Submodel objects — one per selected submodel> ],
  "conceptDescriptions": []
}
```

### Shell Object Structure

```json
{
  "modelType": "AssetAdministrationShell",
  "id": "{base_url}/aas/{systemId}",
  "idShort": "{systemId}_AAS",
  "assetInformation": {
    "assetKind": "Instance",
    "globalAssetId": "{base_url}/assets/{systemId}"
  },
  "submodels": [
    {
      "type": "ModelReference",
      "keys": [{ "type": "Submodel", "value": "<submodel-id>" }]
    }
  ]
}
```

- **`id`**: use the pattern `{base_url}/aas/{systemId}` — derive `systemId` from the asset name
  (no spaces, camelCase or PascalCase)
- **`idShort`**: `{systemId}_AAS`
- **`globalAssetId`**: `{base_url}/assets/{systemId}`
- The `submodels` array in the shell MUST reference EVERY submodel in the `submodels` array by id

---

## Submodel ID Convention

Every submodel id follows:
```
{base_url}/submodels/instances/{systemId}/{idShort}
```

Example for base_url = `https://smartproductionlab.aau.dk`, systemId = `MyRobot`:
- DigitalNameplate → `https://smartproductionlab.aau.dk/submodels/instances/MyRobot/DigitalNameplate`
- Skills → `https://smartproductionlab.aau.dk/submodels/instances/MyRobot/Skills`
- OperationalData → `https://smartproductionlab.aau.dk/submodels/instances/MyRobot/OperationalData`

---

## Mandatory Submodels — ALWAYS Required

**DigitalNameplate** and **HierarchicalStructures** MUST always be present, even if not explicitly
listed. They are required by the SHACL core shape for all ResourceAAS instances.

---

## Submodel Dependency Rules — ENFORCE STRICTLY

These rules are validated by SHACL and will cause violations if broken:

1. **Skills ↔ Capabilities are mutually required**: If Skills is present → Capabilities MUST be
   present. If Capabilities is present → Skills MUST be present.

2. **AID required when Skills/OperationalData/Parameters exist**: If any of Skills, OperationalData,
   or Parameters are present → AID submodel MUST be present.

3. **Skills require AID interface link**: Each Skill MUST be accessible through a SkillInterface
   that is linked to a ResourceInterface in the AID submodel.

4. **Each Skill gets exactly one SkillInterface**: Validate that each skill has exactly one
   `accessibleThrough` relation.

5. **AID requires at least one ResourceInterface**: If AID exists, at least one interface must be
   present in the InteractionMetadata.

6. **Capabilities must link to Skills via realizedBy**: Each Capability MUST have a `realizedBy`
   SubmodelElementList containing a RelationshipElement pointing to the corresponding Skill.

7. **Semantic IDs must use the smartproductionlab.aau.dk base**: The `SemanticId` Property inside
   each Skill SMC and each Capability SMC MUST be a URI starting with
   `https://smartproductionlab.aau.dk/` (or `http://smartproductionlab.aau.dk/`).

8. **SerialNumber and ManufacturerName are mandatory in DigitalNameplate**.

9. **YearOfConstruction format**: exactly 4 digits `YYYY` (e.g. `"2023"`).

10. **DateOfManufacture format**: `YYYY-MM-DD` (e.g. `"2023-01-15"`).

---

## Submodel Element Types Reference

| modelType | Required fields | Notes |
|---|---|---|
| `Property` | `idShort`, `valueType`, `value` | valueType: `xs:string`, `xs:anyURI`, `xs:boolean`, `xs:integer`, etc. |
| `MultiLanguageProperty` | `idShort`, `value` | `value` is array of `{language, text}` |
| `SubmodelElementCollection` | `idShort`, `value` | `value` is array of child elements |
| `SubmodelElementList` | `idShort`, `typeValueListElement`, `value` | ordered list of same-type elements |
| `Entity` | `idShort`, `entityType`, `statements` | `entityType`: `SelfManagedEntity` or `CoManagedEntity` |
| `RelationshipElement` | `idShort`, `first`, `second` | each is a ModelReference |
| `ReferenceElement` | `idShort`, `value` | value is a ModelReference |
| `Capability` | `idShort` | formal AAS Capability model type |
| `Operation` | `idShort` | may have `inputVariables`, `outputVariables`, `inoutputVariables` |
| `File` | `idShort`, `contentType`, `value` | value is a URI |

### Reference Types

**ExternalReference** (for semanticId, supplementalSemanticIds):
```json
{
  "type": "ExternalReference",
  "keys": [{ "type": "GlobalReference", "value": "<URI>" }]
}
```

**ModelReference** (for first/second in RelationshipElement, value in ReferenceElement):
```json
{
  "type": "ModelReference",
  "keys": [
    { "type": "Submodel", "value": "<submodel-id>" },
    { "type": "SubmodelElementCollection", "value": "<idShort>" }
  ]
}
```

---

## Common Semantic IDs (use these exact URIs)

| Purpose | URI |
|---|---|
| DigitalNameplate submodel | `https://admin-shell.io/idta/nameplate/3/0/Nameplate` |
| HierarchicalStructures submodel | `https://admin-shell.io/idta/HierarchicalStructures/1/1/Submodel` |
| AID submodel | `https://admin-shell.io/idta/AssetInterfacesDescription/1/0/Submodel` |
| Skills submodel | `https://smartfactory.de/aas/submodel/Skills#1/0` |
| Capabilities submodel | `https://smartfactory.de/aas/submodel/Capabilities#1/0` |
| OperationalData submodel | `https://admin-shell.io/idta/Variables/1/0/Submodel` |
| Parameters submodel | `https://admin-shell.io/idta/Parameters/1/0/Submodel` |
| AIMC submodel | `https://admin-shell.io/idta/AssetInterfacesMappingConfiguration/1/0/Submodel` |
| AID Interface | `https://admin-shell.io/idta/AssetInterfacesDescription/1/0/Interface` |
| AID InteractionMetadata | `https://admin-shell.io/idta/AssetInterfacesDescription/1/0/InteractionMetadata` |
| CapabilitySet | `https://smartfactory.de/aas/submodel/Capabilities#CapabilitySet` |
| Capability container | `https://smartfactory.de/aas/submodel/Capabilities#Capability` |
| realizedBy list | `https://smartfactory.de/aas/submodel/Capabilities#realizedBy` |
| HierarchicalStructures ArcheType | `https://admin-shell.io/idta/HierarchicalStructures/1/1/ArcheType` |
| HierarchicalStructures EntryNode | `https://admin-shell.io/idta/HierarchicalStructures/1/1/EntryNode` |
| HierarchicalStructures Node | `https://admin-shell.io/idta/HierarchicalStructures/1/1/Node` |
| HierarchicalStructures SameAs | `https://admin-shell.io/idta/HierarchicalStructures/1/1/SameAs` |
| HierarchicalStructures Relationship | `https://admin-shell.io/idta/HierarchicalStructures/1/1/HasPart` |
| MQTT protocol | `https://www.w3.org/2019/wot/td/v1/binding/mqtt` |
| HTTP protocol | `https://www.w3.org/2019/wot/td/v1/binding/http` |
| MODBUS protocol | `https://www.w3.org/2019/wot/td/v1/binding/modbus` |
| WoT TD | `https://www.w3.org/2019/wot/td/v1` |
| WoT PropertyAffordance | `https://www.w3.org/2019/wot/td#PropertyAffordance` |
| WoT ActionAffordance | `https://www.w3.org/2019/wot/td#ActionAffordance` |
| WoT EventAffordance | `https://www.w3.org/2019/wot/td#EventAffordance` |
| WoT InteractionAffordance | `https://www.w3.org/2019/wot/td#InteractionAffordance` |

---

## Skill SemanticId URI Convention

Skill SemanticId values (the `Property` named `SemanticId` inside each Skill SMC, and the
`semanticId` on the Operation element) MUST start with `https://smartproductionlab.aau.dk/`.

Example: `https://smartproductionlab.aau.dk/skills/Dispense`

Capability SemanticId values follow the same pattern:
Example: `https://smartproductionlab.aau.dk/capabilities/Dispensing`
