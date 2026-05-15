# Dynamic Predicate Views

This directory contains on-demand inference queries for high-frequency predicates.

Each query is a SPARQL CONSTRUCT and is intended to be executed at read time by planners or API consumers.

## Queries

- resource-at.rq
- product-at.rq
- occupied.rq
- operational.rq
- operational-stoppering-station.rq
- in-range.rq

## Notes

- Queries are authored against an explicit dataset:
	- FROM <urn:kg:tbox>
	- FROM <urn:kg:abox>
- If your deployment uses different graph IRIs, update the FROM clauses in the query before execution.
- These files are intentionally not part of event-triggered materialization.
