# Phase 1 Ontology Layout (Implemented)

This document records the Phase 1 ontology changes applied in kg-bridge.

## Scope Implemented

- Trimmed default APEX language-variant imports to currently used planning expressivity.
- Established core + extension ontology layout.
- Added lightweight axioms for CPPS/CPPM skill provision inference.
- Added APEX capability extension for the main use-case capability set.

## Active Core Expressivity

Loaded by default in the APEX root/bootstrap path:

- `apex-pddl.ttl` (classical structure)
- `apex-pddl-2-1.ttl` (temporal/numeric)
- `apex-pddl-plus.ttl` (processes/events)
- `apex-fond.ttl` (nondeterministic outcomes)
- `apex-execution.ttl` (execution records)

Not imported by default:

- `apex-pddl-3.ttl`
- `apex-ppddl.ttl`

These remain available as optional modules.

## Core + Extension Layout

- Core root: `Ontology/APEX/apex.ttl`
- Core module guide: `Ontology/APEX/README.md`
- Extension directory: `Ontology/APEX/extensions/`
- Extension guide: `Ontology/APEX/extensions/README.md`

Compose bootstrap now loads all `Ontology/APEX/extensions/*.ttl` files into `urn:kg:tbox` after core modules.

## Lightweight Axioms Added

In `Ontology/APEX/apex-resource-hierarchy.ttl`:

- Canonical APEX aliases: `apex:Resource`, `apex:Product` (equivalent to CSS classes).
- Skill provision chain axioms:
  - `css:providesSkill <- apex:hasCPPM o css:providesSkill`
  - `css:providesSkill <- apex:hasCPS o css:providesSkill`

## Main Capability Extension

`Ontology/APEX/extensions/apex-extension-main-capabilities.ttl` defines:

- `apex:MainLineCapability`
- `apex:LoadingCapability`
- `apex:DispensingCapability`
- `apex:StopperingCapability`
- `apex:CappingCapability`
- `apex:QualityControlCapability`
- `apex:UnloadingCapability`
- `apex:MoveToPositionCapability`
