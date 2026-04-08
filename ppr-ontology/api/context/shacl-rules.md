# SHACL Validation Rules — Human-Readable Summary

The generated AAS JSON is validated by pyshacl against four shape files. All of these rules will be
checked; violations will be reported back and used to prompt a corrected generation.

---

## Core Rules (`resourceaas-core.shacl.ttl`)

These apply to **every** ResourceAAS regardless of submodel selection:

- **[VIOLATION]** `DigitalNameplate` submodel MUST be present (exactly 1).
  → `idShort: "DigitalNameplate"` must appear in the submodels array.

- **[VIOLATION]** `HierarchicalStructures` submodel MUST be present (exactly 1).
  → `idShort: "HierarchicalStructures"` must appear in the submodels array.

---

## Dependency Rules (`resourceaas-dependencies.shacl.ttl`)

Cross-submodel structural constraints:

- **[VIOLATION]** If Skills, OperationalData, or Parameters submodel exists → **AID submodel MUST also exist**.
  → `idShort: "AID"` must be present.

- **[VIOLATION]** If Skills are present → a SoftwareInterface (ResourceInterface in AID) MUST be linked to each Skill's SkillInterface.
  → Each skill's Operation element must be accessible through a SkillInterface that references a ResourceInterface.

- **[VIOLATION]** Each provided Skill must expose **exactly one SkillInterface**.
  → In the AID submodel, exactly one interface must map to each skill via the AIMC/Skills linkage.

- **[VIOLATION]** If AID submodel exists → at least one ResourceInterface MUST be mapped.
  → The AID must have at least one Interface SMC inside its submodelElements.

- **[VIOLATION]** Each SkillInterface must reference a ResourceInterface from the **same Resource**.

- **[VIOLATION]** Skills submodel present → Capabilities submodel MUST be present (and vice versa).
  → Skills and Capabilities are always paired.

- **[VIOLATION]** If Resource provides Skills → it MUST provide at least one Capability.

- **[VIOLATION]** If Resource provides Capabilities → it MUST provide at least one Skill.

- **[VIOLATION]** Each Capability MUST be linked via `isRealizedBySkill` to a Skill.
  → In the Capabilities submodel, each capability SMC must contain a `realizedBy` SubmodelElementList
    with a RelationshipElement whose `second` key points to the corresponding skill in the Skills submodel.

---

## Semantic Rules (`resourceaas-semantics.shacl.ttl`)

- **[VIOLATION]** Each Capability's `SemanticId` Property value MUST match `^https?://smartproductionlab\.aau\.dk/`.

- **[VIOLATION]** Each Skill's `SemanticId` Property value MUST match `^https?://smartproductionlab\.aau\.dk/`.

- **[VIOLATION]** `serialNumber` must not be mapped more than once (maxCount 1).

- **[VIOLATION]** `yearOfConstruction` must be a 4-digit year — pattern `^[0-9]{4}$`.
  → e.g. `"2023"` is valid; `"2023-01-01"` is not.

- **[VIOLATION]** `dateOfManufacture` must follow YYYY-MM-DD — pattern `^[0-9]{4}-[0-9]{2}-[0-9]{2}$`.

- **[VIOLATION]** If DigitalNameplate is present → both `SerialNumber` Property AND `ManufacturerName`
  MultiLanguageProperty MUST be present in the submodelElements.

---

## BoM Rules (`resourceaas-bom.shacl.ttl`)

- **[VIOLATION]** `HierarchicalStructures.Name` (the `ArcheType` property's companion — used as the
  `EntryNode` entity's `idShort`) is required. The EntryNode entity MUST exist.

- **[VIOLATION]** Each BoM entity (HasPart / IsPartOf node) MUST have a `globalAssetId`.
  → Each child Entity element inside the EntryNode's statements MUST have `"entityType": "SelfManagedEntity"` and a `"globalAssetId"` field.

- **[WARNING]** If an Archetype is set but no entity entries are defined yet, a warning is raised
  (not a violation — the AAS is still valid).

---

## Quick Checklist Before Outputting

☐ `DigitalNameplate` submodel present with `SerialNumber` and `ManufacturerName`
☐ `HierarchicalStructures` submodel present with an EntryNode entity
☐ If Skills → Capabilities also present (and vice versa)
☐ If Skills/OperationalData/Parameters → AID also present
☐ All Capability SemanticId values start with `https://smartproductionlab.aau.dk/`
☐ All Skill SemanticId values start with `https://smartproductionlab.aau.dk/`
☐ Each Capability has a `realizedBy` list pointing to a Skill
☐ AID has at least one interface in submodelElements
☐ All submodel IDs are referenced in the shell's `submodels` array
