#!/usr/bin/env bash
# E2E bootstrap (plan .kilo/plans/1788416400000-e2e-station-bindings-plan.md,
# Phase 6): initializes Registration_Service's aas-model submodule, packages the
# Java DMP, brings the isolated e2e stack up and checks managed convergence.
# The checked-in resource descriptions and Python simulator are not regenerated.
#
#   registration-service healthy -> station publishes config -> AAS on aas-env
#   -> shared Java DMP discovers/compiles AIMCs and reconciles Kafka events.
#
# Usage:  compose/e2e/bootstrap.sh [--no-build] [--no-stack]
# Requires: docker, maven (on PATH or /tmp/kilo/apache-maven-*), JDK 17.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
E2E_DIR="$REPO_ROOT/compose/e2e"
COMPOSE_FILE="$REPO_ROOT/compose/docker-compose.e2e.yml"

# Ports (must match compose/docker-compose.e2e.yml defaults).
export E2E_MQTT_PORT="${E2E_MQTT_PORT:-18830}"
export E2E_AAS_PORT="${E2E_AAS_PORT:-18081}"
export E2E_KAFKA_PORT="${E2E_KAFKA_PORT:-19092}"
export E2E_DMP_PORT="${E2E_DMP_PORT:-18086}"

BUILD_IMAGES=true
START_STACK=true
for arg in "$@"; do
  case "$arg" in
    --no-build) BUILD_IMAGES=false ;;
    --no-stack) START_STACK=false ;;
    *) echo "unknown arg: $arg"; exit 2 ;;
  esac
done

log() { echo "[bootstrap] $*"; }
mkdir -p "$E2E_DIR/aas"

# ---------------------------------------------------------------- model submodule
init_model() {
  # Registration_Service builds from its pinned aas-model submodule.
  git -C "$REPO_ROOT/Registration_Service" submodule update --init --recursive
  log "Registration_Service aas-model: $(git -C "$REPO_ROOT/Registration_Service/aas-model" rev-parse --short HEAD)"
}

# ---------------------------------------------------------------- java image
build_dmp() {
  if ! command -v mvn >/dev/null 2>&1; then
    local candidate
    candidate="$(ls -d /tmp/kilo/apache-maven-* 2>/dev/null | sort | tail -1 || true)"
    if [[ -n "${candidate:-}" ]]; then
      export PATH="$candidate/bin:$PATH"
      export JAVA_HOME="${JAVA_HOME:-/tmp/jdk-17.0.2}"
      log "using maven from $candidate"
    else
      log "ERROR: maven not found (needed to package the Java DMP)"; exit 1
    fi
  fi
  ( cd "$REPO_ROOT/aas-camel-dmp" \
      && mvn -o -B -Ddocker.skip=true -DskipTests -pl dmp.component -am \
             clean package dependency:copy-dependencies \
             -DincludeScope=runtime -DoutputDirectory=target/lib )
  log "Java DMP packaged with current reactor dependencies"
}

# ---------------------------------------------------------------- main
if $BUILD_IMAGES; then
  init_model
  build_dmp
fi

if $START_STACK; then
  if $BUILD_IMAGES; then
    log "building e2e images (registration-service, Python station, shared Java DMP)"
    docker compose -f "$COMPOSE_FILE" build
  fi
  log "starting e2e stack"
  docker compose -f "$COMPOSE_FILE" up -d --no-build --wait --wait-timeout 300 \
    mosquitto mongo kafka aas-env registration-service stoppering_station dmp

  log "waiting for shared Java DMP mappings to converge"
  deadline=$(( $(date +%s) + 180 ))
  until curl -fsS "http://localhost:${E2E_DMP_PORT}/management/status" \
      | python3 -c 'import json, sys; s = json.load(sys.stdin); sys.exit(0 if s.get("converged") and s.get("installedMappings", 0) > 0 else 1)' \
      >/dev/null 2>&1; do
    if (( $(date +%s) > deadline )); then
      log "ERROR: shared Java DMP did not converge; blocked mappings are not readiness"
      curl -s "http://localhost:${E2E_DMP_PORT}/management/status" || true
      docker compose -f "$COMPOSE_FILE" logs --tail 30 dmp
      exit 1
    fi
    sleep 3
  done

  log "E2E STACK READY"
  log "  AAS:   http://localhost:${E2E_AAS_PORT}"
  log "  MQTT:  localhost:${E2E_MQTT_PORT}"
  log "  DMP:   http://localhost:${E2E_DMP_PORT}  (host tests)"
  log "  AAS delegation: http://dmp:8080/operations/{aasIdShort}/{skill}"
fi
