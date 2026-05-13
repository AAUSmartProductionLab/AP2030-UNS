# kg-bridge

## Local Development

Install runtime + test dependencies and run the conversion-layer tests:

```bash
pip install -r kg-bridge/requirements.txt -r kg-bridge/requirements-dev.txt -e py-aas-rdf
PYTHONPATH=kg-bridge pytest kg-bridge/tests -v
```

## Inference Split

The bridge now separates inference into two categories:

- Structural, low-churn enrichment is materialized at event time from [sparql/materialization](sparql/materialization).
- Dynamic, high-frequency state predicates are evaluated on demand as SPARQL CONSTRUCT views from [sparql/views](sparql/views).

Dynamic runtime views currently include:

- `resource-at.rq`
- `product-at.rq`
- `occupied.rq`
- `operational.rq`
- `in-range.rq`

## Named Graphs

- `urn:kg:tbox`: ontology vocabulary and axioms (AAS metamodel, CSS, ARSO, APEX)
- `urn:kg:abox`: instance data from AAS events and structural materialization outputs
- `urn:kg:shacl`: SHACL shapes used for validation workflows

By default, event projection and materialization write to `urn:kg:abox`. Dynamic view queries include `FROM <urn:kg:tbox>` and `FROM <urn:kg:abox>` so they can resolve both schema and instance data.
