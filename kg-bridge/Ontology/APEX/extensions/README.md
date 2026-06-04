# APEX Extensions Governance

## Purpose

Extensions let us add domain-specific types, predicates, and capability taxonomies
without editing the APEX core.

## Naming and Versioning

- Namespace base: `https://w3id.org/2026/apex/extensions/`
- File naming: `apex-extension-<domain>.ttl`
- Ontology IRI example: `https://w3id.org/2026/apex/extensions/main-capabilities`

## Rules

- Extensions must be additive.
- Extensions must import `https://w3id.org/2026/apex/`.
- Core identifiers should not be redefined.
- Deprecated identifiers should be retained as aliases where practical.

## Loading Behavior

Compose bootstrap loads `extensions/*.ttl` into `urn:kg:tbox` after core modules.
Missing extension files are skipped.
