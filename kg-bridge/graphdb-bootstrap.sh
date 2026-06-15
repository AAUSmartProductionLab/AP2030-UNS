#!/bin/sh
# Bootstrap GraphDB with ontology TBox, SHACL shapes, and deployment ABox seeds.
set -eu

GRAPHDB_BASE="${GRAPHDB_BASE:-http://kg-graphdb:7200}"
TBOX_GRAPH="${KG_TBOX_GRAPH:-urn:kg:tbox}"
ABOX_GRAPH="${KG_ABOX_GRAPH:-urn:kg:abox}"
SHACL_GRAPH="${KG_SHACL_GRAPH:-urn:kg:shacl}"

# Delete repository if it already exists (RDF4J Server API, ignore 404).
echo "Removing existing 'kg' repository if present..."
curl -fsS -X DELETE "${GRAPHDB_BASE}/repositories/kg" > /dev/null 2>&1 || true

# Create repository via RDF4J Server PUT with Turtle config.
echo "Creating repository 'kg'..."
cat > /tmp/repo-config.ttl <<'CONFIG'
@prefix rep: <http://www.openrdf.org/config/repository#>.
@prefix sr: <http://www.openrdf.org/config/repository/sail#>.
@prefix sail: <http://www.openrdf.org/config/sail#>.
@prefix graphdb: <http://www.ontotext.com/config/graphdb#>.
[] a rep:Repository ;
   rep:repositoryID "kg" ;
   rep:repositoryImpl [
      rep:repositoryType "graphdb:SailRepository" ;
      sr:sailImpl [
         sail:sailType "graphdb:Sail" ;
         graphdb:ruleset "empty" ;
         graphdb:base-URL "urn:kg:abox" ;
         graphdb:checkForInconsistencies "false" ;
         graphdb:ignoreInvalidStatements "true" ;
         graphdb:enableContextIndex "true" ;
         graphdb:enablePredicateList "true"
      ]
   ].
CONFIG
curl -fsS -X PUT "${GRAPHDB_BASE}/repositories/kg" \
  -H "Content-Type: application/x-turtle" \
  --data-binary @/tmp/repo-config.ttl

# Simple IRI-to-URL encoder (encodes <>:/# for safe URL embedding).
encode_iri() {
  echo "$1" | sed 's/</%3C/g; s/>/%3E/g; s/:/%3A/g; s/#/%23/g'
}

load_url() {
  graph="$1"
  file="$2"
  [ -f "$file" ] || { echo "Skipping (not found): $file"; return 0; }
  # GraphDB context must be an N-Triples resource, i.e. wrapped in <>.
  encoded=$(encode_iri "<${graph}>")
  echo "Loading $file -> $graph"
  curl -fsS -X POST \
    -H "Content-Type: text/turtle" \
    --data-binary @"$file" \
    "${GRAPHDB_BASE}/repositories/kg/statements?context=${encoded}"
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

echo "GraphDB bootstrap complete."
