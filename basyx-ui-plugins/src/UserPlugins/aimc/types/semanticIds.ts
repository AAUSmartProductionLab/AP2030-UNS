/**
 * Semantic IDs the AIMC plugin relies on. Kept in sync with
 * `aas_model.constants` and `ARSO_Ontology_AAS_Generation/ui/src/aas/semanticIds.ts`.
 *
 * Only the ids that are actually matched are declared here: the parser resolves
 * the remaining children of a route (`Source`, `Sink`, `SourceId`, …) by
 * `idShort`, which survives the AAS round trip, while `semanticId` on
 * `SubmodelElementList` items is stripped by AASd-114.
 */

const BASE = 'https://admin-shell.io/idta/AssetInterfacesMappingConfiguration'

/** AIMC 2.0 submodel — what this repository's templates generate. */
export const AIMC_SUBMODEL = `${BASE}/2/0/Submodel`
/** AIMC 1.0 submodel, still emitted by some tooling. */
export const AIMC_SUBMODEL_V1 = `${BASE}/1/0/Submodel`

export const AIMC_TRANSFORMATION = `${BASE}/2/0/MappingConfiguration/Transformation`
export const AIMC_SOURCES = `${BASE}/2/0/MappingConfiguration/Sources`
export const AIMC_SINKS = `${BASE}/2/0/MappingConfiguration/Sinks`

/** DMP extension: the optional correlated-reply direction of an operation mapping. */
export const AIMC_RESPONSE_TRANSFORMATION = `${BASE}/2/0/MappingConfiguration/ResponseTransformation`

/** Concept qualifier that marks a property write-delegation mapping. */
export const WRITE_DELEGATION_QUALIFIER = 'writeDelegation'

/**
 * Semantic IDs the plugin registers for. Both AIMC 2.0 and 1.0 submodels are
 * handled; the structure is identical apart from the version segment.
 *
 * Note that a route cannot be registered for: AASd-114 makes every
 * `SubmodelElementList` item inherit the list's `semanticId`, so
 * `aas_pydantic` strips the per-item one and the BaSyx UI cannot dispatch a
 * plugin on an individual route.
 */
export const AIMC_PLUGIN_SEMANTIC_IDS = [AIMC_SUBMODEL, AIMC_SUBMODEL_V1]
