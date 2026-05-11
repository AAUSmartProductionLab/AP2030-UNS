# kg-bridge

## Local Development

Install runtime + test dependencies and run the conversion-layer tests:

```bash
pip install -r kg-bridge/requirements.txt -r kg-bridge/requirements-dev.txt -e py-aas-rdf
PYTHONPATH=kg-bridge pytest kg-bridge/tests -v
```
