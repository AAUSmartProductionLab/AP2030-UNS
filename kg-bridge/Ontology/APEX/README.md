# APEX Ontology Layout (Phase 1)

This folder is organized into a core ontology and optional extensions.

## Core Modules (loaded by default)

- `apex.ttl`
- `apex-predicates.ttl`
- `apex-product-hierarchy.ttl`
- `apex-resource-hierarchy.ttl`
- `apex-pddl.ttl`
- `apex-pddl-2-1.ttl`
- `apex-pddl-plus.ttl`
- `apex-fond.ttl`
- `apex-execution.ttl`
- `apex-shacl.ttl`

These modules cover the currently used planning/execution expressivity:
- classical PDDL structures
- temporal constructs and process/event modeling
- FOND nondeterministic outcomes

## Optional Modules (not loaded by default)

- `apex-pddl-3.ttl`
- `apex-ppddl.ttl`

These stay in-repo for compatibility and future use, but are not part of the default T-Box bootstrap.

## Extensions

Extension files live in `extensions/` and are loaded after core modules by Fuseki bootstrap.
Each extension should:
- declare its own ontology IRI
- import `https://w3id.org/2026/apex/`
- add only additive vocabulary/axioms
- avoid changing core module semantics
