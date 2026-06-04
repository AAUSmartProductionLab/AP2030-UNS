# KG Contract (Phase 0 Draft)

This document captures the Phase 0 standards baseline for making the KG the shared contract between ingestion, planning, and execution.

Namespace decision (accepted):
- For planning and execution concepts, semantic IDs and type identifiers use the APEX namespace as canonical.
- This includes predicate identifiers, action vocabulary identifiers, variable semantic IDs, and planning/execution type hierarchy identifiers.

Scope:
- Define the contract surface without changing runtime behavior.
- Record what is already implemented vs what is contract-defined for upcoming phases.

Out of scope:
- Planner migration to SPARQL.
- Controller SPARQL predicate evaluation and write-back.
- Ontology module trimming.

## 1. Namespaces

| Prefix | Namespace |
| --- | --- |
| `apex` | `https://w3id.org/2026/apex/` |
| `arso` | `https://w3id.org/2025/arso#` |
| `arsox` | `https://w3id.org/aau-ra/arso-ext#` |
| `css` | `http://www.w3id.org/hsu-aut/css#` |
| `aas` | `https://admin-shell.io/aas/3/1/` |
| `sh` | `http://www.w3.org/ns/shacl#` |

Source files:
- `Ontology/APEX/apex.ttl`
- `Ontology/APEX/apex-pddl.ttl`
- `Ontology/APEX/apex-resource-hierarchy.ttl`
- `Ontology/APEX/apex-predicates.ttl`
- `Ontology/APEX/apex-shacl.ttl`
- `Ontology/arso-extensions.ttl`

## 2. Predicate + Type Vocabulary Contract

Current predicate classes:
- `apex:ResourceAt(Resource, LocationLiteral)`
- `apex:ProductAt(Product, LocationLiteral)`
- `apex:Occupied(Resource)`
- `apex:Operational(Resource)`
- `apex:InRange(Resource, StationLikeResource)`

Current argument encoding:
- Predicates are represented as reified facts (`rdf:type apex:PredicateSubclass`).
- Arguments are represented with `apex:PredicateArgumentBinding`.
- Required binding fields:
  - `apex:argumentIndex` (1-based)
  - exactly one of `apex:argumentObject` or `apex:argumentLiteral`

Current type hierarchy anchors:
- `apex:Resource`, `apex:Product`
- `apex:CPPS`, `apex:CPPM`, `apex:CPS`
- concrete subclasses under `apex-resource-hierarchy.ttl`

Compatibility note:
- Existing CSS classes and properties remain usable for interoperability, but planning/execution contracts resolve to APEX identifiers.

Contract rule:
- Every predicate argument type referenced by action schemas must resolve to classes available through the active T-Box import set.

## 3. Action Representation + Projection Contract

### 3.1 Minimal action shape (contract)

The projected planning-domain representation in KG uses:
- `apex:Action`
- `apex:hasParameter`
- `apex:hasPrecondition`
- `apex:hasEffect`

Temporal and nondeterministic extensions remain available:
- temporal: `apex:DurativeAction`, `apex:hasAtStartCondition`, `apex:hasAtEndEffect`, ...
- fond: `apex:NondeterministicEffect`, `apex:OneOf`

Decision:
- Projection scope is full PDDL concept coverage used by this stack, including temporal constructs and FOND/nondeterministic constructs.

### 3.2 Projection contract (Phase 0 definition)

Projection from raw AAS AI-Planning RDF to `apex:Action` shape is defined as a required bridge responsibility.

Status:
- Implemented now: shell/submodel typing and mirrored SubmodelElement projection in `conversion/projection.py`.
- Defined for next implementation step: action/precondition/effect lifting query set with temporal and FOND coverage.

### 3.3 Runtime problem inference contract

Problem inference must be query-driven:
- Objects: inferred from KG instances (resources, products, orders, locations).
- Init: inferred from asserted state + computed view facts.
- Goal: inferred from Order AAS projection.

No `apex:Problem` authoring is required in AAS payloads once planner migration is complete.

## 4. Capability Taxonomy Contract

Phase 0 taxonomy baseline is captured in:
- `contracts/capability-taxonomy.phase0.yaml`

Planning unit:
- Skills are the planning-level actions.

Current resource selection mode:
- Explicit resource assignment is used in this stack today; capability-based matching is not active.

Capability role in current scope:
- Capabilities are retained as domain vocabulary, process semantics, and compatibility mapping metadata.

Main capability set for this use case:
- Loading
- Dispensing
- Stoppering
- Capping
- QualityControl
- Unloading
- MoveToPosition

Bridge relation:
- `css:isRealizedBySkill` is the normalized relation between capability and skill.
- Current materialization source: `sparql/materialization/030-capability-skill-realization.rq`.

## 5. Predicate Dispatch Contract

Phase 0 dispatch baseline is captured in:
- `contracts/predicate-dispatch.phase0.yaml`

Required fields per predicate:
- evaluation mode (`computed` or `asserted`)
- argument types
- strategy id
- strategy query/view
- strategy parameters

## 6. Semantic-ID Convention + Variable Contracts

Phase 0 baseline is captured in:
- `contracts/semantic-id-contract.phase0.yaml`

Contract intent:
- Operational variables used by strategy views must be bound by semantic ID rather than path regex.
- Each planning/execution asset type must declare required variables and their semantic IDs in APEX namespace.

Status:
- Existing runtime views still use path regex matching.
- Semantic-ID contracts are now versioned and can be enforced in a later migration step.

## 7. SHACL Contract

Current SHACL in repo validates predicate argument bindings:
- `apex:PredicateArgumentBindingShape`
- `apex:PredicateShape`

Phase 0 required gate shape targets to add in next steps:
- resource has location binding
- every referenced predicate is defined
- every projected action references an existing skill
- each CPPM belongs to exactly one CPPS

Decision:
- SHACL gate policy is fail-fast. If SHACL validation fails, planning must stop and return validation errors.

## 8. Exit Criteria for This Phase-0 Start

Completed in this change set:
- dead `live` module removed
- stale duplicate live tests removed
- KG contract draft added
- dispatch + semantic-id contract seed files added

Still open inside Phase 0:
- implement action-shape projection queries with full temporal and FOND coverage