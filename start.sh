#!/usr/bin/env sh
# Starts all claim-runner services in dependency order.
# Data Service must be healthy before adjudication services are started.

set -e

DATA_PORT=${DATA_PORT:-8083}
BENEFITS_PORT=${BENEFITS_PORT:-8081}
PRICER_PORT=${PRICER_PORT:-8082}
CLAIMS_PORT=${CLAIMS_PORT:-8080}

wait_for_health() {
    url=$1
    service=$2
    echo "Waiting for ${service} at ${url} ..."
    i=0
    while [ $i -lt 30 ]; do
        if curl -sf "${url}" > /dev/null 2>&1; then
            echo "${service} is UP."
            return 0
        fi
        sleep 1
        i=$((i + 1))
    done
    echo "ERROR: ${service} did not become healthy within 30 seconds." >&2
    exit 1
}

# --- 1. Data Service (no upstream dependencies) ---
echo "Starting Data Service on port ${DATA_PORT} ..."
(cd data_service && PORT=${DATA_PORT} uvicorn main:app --host 0.0.0.0 --port ${DATA_PORT}) &

wait_for_health "http://localhost:${DATA_PORT}/health" "Data Service"

# --- 2. Benefits Determiner (depends on Data Service) ---
echo "Starting Benefits Determiner on port ${BENEFITS_PORT} ..."
PORT=${BENEFITS_PORT} uvicorn benefits_determiner.main:app --host 0.0.0.0 --port ${BENEFITS_PORT} &

wait_for_health "http://localhost:${BENEFITS_PORT}/health" "Benefits Determiner"

# --- 3. Pricer (depends on Data Service) ---
echo "Starting Pricer on port ${PRICER_PORT} ..."
PORT=${PRICER_PORT} uvicorn pricer.main:app --host 0.0.0.0 --port ${PRICER_PORT} &

wait_for_health "http://localhost:${PRICER_PORT}/health" "Pricer"

# --- 4. Claims Manager (depends on Benefits Determiner + Pricer) ---
# NOTE: Benefits Determiner (step 2) remains a TODO until spec 002 is implemented.
echo "Starting Claims Manager on port ${CLAIMS_PORT} ..."
PORT=${CLAIMS_PORT} uvicorn claims_manager.main:app --host 0.0.0.0 --port ${CLAIMS_PORT} &

wait_for_health "http://localhost:${CLAIMS_PORT}/health" "Claims Manager"

echo "All services started."
wait
