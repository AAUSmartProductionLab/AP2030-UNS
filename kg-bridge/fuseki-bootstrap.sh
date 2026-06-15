#!/bin/sh
# Bootstrap Fuseki with ontology TBox, SHACL shapes, and deployment ABox seeds.
set -eu

BASE="${FUSEKI_BASE:-http://kg-fuseki:3030/kg}"
TBOX_GRAPH="${KG_TBOX_GRAPH:-urn:kg:tbox}"
ABOX_GRAPH="${KG_ABOX_GRAPH:-urn:kg:abox}"
SHACL_GRAPH="${KG_SHACL_GRAPH:-urn:kg:shacl}"

load_url() {
  graph="$1"
  file="$2"
  [ -f "$file" ] || { echo "Skipping (not found): $file"; return 0; }
  echo "Loading $file -> $graph"
  curl -fsS -u "admin:${ADMIN_PASSWORD:-admin}" \
    -X POST -H "Content-Type: text/turtle" \
    --data-binary @"$file" \
    "${BASE}/data?graph=${graph}"
}

# ── TBox: ARSO ontologies ──
load_url "$TBOX_GRAPH" /staging/arso/AAS/aas-rdf-ontology.ttl
load_url "$TBOX_GRAPH" /staging/arso/CSS/CSS-Ontology.ttl
load_url "$TBOX_GRAPH" /staging/arso/ARSO/ARSO_AAS.ttl
for f in /staging/arso/ARSO/Modules/*.ttl; do
  load_url "$TBOX_GRAPH" "$f"
done

# ── TBox: kg-bridge ontologies ──
load_url "$TBOX_GRAPH" /staging/kg-ontology/arso-extensions.ttl
for f in /staging/kg-ontology/APEX/*.ttl; do
  [ -f "$f" ] || continue
  case "${f##*/}" in
    apex-shacl.ttl) ;;
    *) load_url "$TBOX_GRAPH" "$f" ;;
  esac
done
for f in /staging/kg-ontology/APEX/extensions/*.ttl; do
  [ -f "$f" ] || continue
  load_url "$TBOX_GRAPH" "$f"
done

# ── SHACL ──
for d in /staging/arso/SHACL/Manual /staging/arso/SHACL/Generated; do
  for f in "$d"/*.ttl; do
    load_url "$SHACL_GRAPH" "$f"
  done
done
load_url "$SHACL_GRAPH" /staging/kg-ontology/APEX/apex-shacl.ttl

# ── ABox deployment seeds ──
deployment_loaded=0
for f in /staging/kg-ontology/deployment/*.ttl; do
  [ -f "$f" ] || continue
  deployment_loaded=1
  load_url "$ABOX_GRAPH" "$f"
done
[ "$deployment_loaded" -eq 0 ] && echo "No deployment ABox seed files found in /staging/kg-ontology/deployment"

echo "Bootstrap complete."
