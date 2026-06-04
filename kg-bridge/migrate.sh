#!/usr/bin/env bash
set -euo pipefail

FUSEKI_UPDATE_URL="${FUSEKI_UPDATE_URL:-http://localhost:3030/kg/update}"
FUSEKI_USER="${FUSEKI_USER:-admin}"
FUSEKI_PASSWORD="${FUSEKI_PASSWORD:-admin}"
AAS_GRAPH="${AAS_GRAPH:-}"
ABOX_GRAPH="${KG_ABOX_GRAPH:-${AAS_GRAPH:-urn:kg:abox}}"

echo "Dropping Fuseki ABox graph: ${ABOX_GRAPH}"
curl -fsS -u "${FUSEKI_USER}:${FUSEKI_PASSWORD}" \
  -X POST "${FUSEKI_UPDATE_URL}" \
  --data-urlencode "update=DROP GRAPH <${ABOX_GRAPH}>"

echo "Done. Start kg-bridge to rebuild ABox content from events. TBox and SHACL graphs are preserved."
