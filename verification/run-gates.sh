#!/bin/bash
set -Eeuo pipefail

export PROJECT_NAME="abst_gp_v52_validation"
export COMPOSE_FILE="verification/docker-compose.test.yml"
KEEP_ENV="${KEEP_ENV:-0}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
ARTIFACTS_DIR="artifacts/verification/v5.2.1/${TIMESTAMP}"

mkdir -p "$ARTIFACTS_DIR"
cd "$(dirname "$0")/.."

echo "============================================="
echo "INICIANDO SPRINT V5.2.1 - CHECKPOINT 3"
echo "============================================="

if [[ "$PROJECT_NAME" != "abst_gp_v52_validation" ]]; then
    echo "ERROR: PROJECT_NAME no es el autorizado."
    exit 1
fi

declare -A RESULTS

function run_compose() {
    docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" "$@"
}

function cleanup() {
    echo "--- Ejecutando Cleanup ---"
    if [[ "$PROJECT_NAME" == "abst_gp_v52_validation" ]]; then
        if [[ "$KEEP_ENV" == "1" ]]; then
            echo "KEEP_ENV=1: Omitiendo cleanup de contenedores."
        else
            # Save logs before removing containers
            run_compose logs > "$ARTIFACTS_DIR/docker-compose.log" || true
            run_compose down -v --remove-orphans
        fi
    fi
}
trap cleanup EXIT

# A. PREFLIGHT
echo "[A] Preflight..."
docker --version > "$ARTIFACTS_DIR/versions.txt"
docker compose version >> "$ARTIFACTS_DIR/versions.txt"
run_compose config > "$ARTIFACTS_DIR/compose-config.yml"
RESULTS["PREFLIGHT"]="PASS"

# B. BUILD IMÁGENES
echo "[B] Build Imágenes..."
run_compose build > "$ARTIFACTS_DIR/compose-build.log" 2>&1 || { RESULTS["BUILD"]="FAIL"; exit 1; }
RESULTS["BUILD"]="PASS"

# C. FRONTEND
echo "[C] Frontend Build & Check..."
# Ya se ejecutó npm ci y build dentro del Dockerfile, pero se requiere confirmación en la misma imagen
run_compose run --rm frontend-test sh -c "npm ci --legacy-peer-deps && npm run build" > "$ARTIFACTS_DIR/npm-ci.log" 2>&1 || { RESULTS["FRONTEND"]="FAIL"; exit 1; }
RESULTS["FRONTEND"]="PASS"

# D. DEPENDENCIAS
echo "[D] Dependencias (PostgreSQL, Redis)..."
run_compose up -d db-test redis-test
echo "Esperando healthchecks..."
sleep 10
RESULTS["DEPENDENCIAS"]="PASS"

# E. ALEMBIC
echo "[E] Alembic Migrations..."
run_compose run --rm backend-test alembic upgrade head > "$ARTIFACTS_DIR/alembic.log" 2>&1 || { RESULTS["ALEMBIC"]="FAIL"; exit 1; }
RESULTS["ALEMBIC"]="PASS"

# F. BACKEND SUITE
echo "[F] Backend Suite Completa..."
run_compose run --rm backend-test python -m pytest tests/ -v --ignore=tests/e2e > "$ARTIFACTS_DIR/pytest-full.log" 2>&1 || { RESULTS["SUITE_BACKEND"]="FAIL"; exit 1; }
RESULTS["SUITE_BACKEND"]="PASS"

# G. CONCURRENCIA
echo "[G] Prueba Real de Concurrencia..."
run_compose run --rm backend-test python -m pytest tests/api/integration/test_comparison_concurrency.py -v > "$ARTIFACTS_DIR/concurrency.log" 2>&1 || { RESULTS["CONCURRENCY"]="FAIL"; exit 1; }
RESULTS["CONCURRENCY"]="PASS"

# H. ROLLBACK
echo "[H] Prueba Real de Rollback..."
run_compose run --rm backend-test python -m pytest tests/api/integration/test_comparison_rollback.py -v > "$ARTIFACTS_DIR/rollback.log" 2>&1 || { RESULTS["ROLLBACK"]="FAIL"; exit 1; }
RESULTS["ROLLBACK"]="PASS"

# I. DOCUMENTAL SECURITY
echo "[I] Gate Documental (Seguridad)..."
run_compose run --rm backend-test python -m pytest tests/e2e/test_documental_security.py -v > "$ARTIFACTS_DIR/documental.log" 2>&1 || { RESULTS["DOCUMENTAL"]="FAIL"; exit 1; }
RESULTS["DOCUMENTAL"]="PASS"

# J. API E2E
echo "[J] API E2E..."
run_compose up -d backend-app worker-test
echo "Esperando a backend y worker..."
sleep 15
run_compose run --rm backend-test python -m pytest tests/e2e/test_full_document_pipeline.py -v > "$ARTIFACTS_DIR/api_e2e.log" 2>&1 || { RESULTS["API_E2E"]="FAIL"; exit 1; }
RESULTS["API_E2E"]="PASS"

# K. BROWSER E2E
echo "[K] Browser E2E..."
# Frontend ya debería estar corriendo en background para ser probado
run_compose up -d frontend-test
echo "Instalando Playwright dependencias en test container y ejecutando pruebas..."
run_compose run --rm browser-test sh -c "npm install && npx playwright install --with-deps chromium && npm run test" > "$ARTIFACTS_DIR/browser_e2e.log" 2>&1 || { RESULTS["BROWSER_E2E"]="FAIL"; exit 1; }
RESULTS["BROWSER_E2E"]="PASS"

# L. REPORTE
echo "--- GENERANDO REPORTE MATRIZ ---"
REPORT_FILE="$ARTIFACTS_DIR/gate-summary.md"
echo "# Resumen del Gate V5.2.1 Checkpoint 3" > "$REPORT_FILE"
echo "" >> "$REPORT_FILE"
echo "| Gate | Estado |" >> "$REPORT_FILE"
echo "|------|--------|" >> "$REPORT_FILE"
GATES=("PREFLIGHT" "BUILD" "FRONTEND" "DEPENDENCIAS" "ALEMBIC" "SUITE_BACKEND" "CONCURRENCY" "ROLLBACK" "DOCUMENTAL" "API_E2E" "BROWSER_E2E")
for gate in "${GATES[@]}"; do
    state=${RESULTS[$gate]:-SKIPPED}
    echo "| $gate | $state |" >> "$REPORT_FILE"
    echo "$gate: $state"
done

# Evaluar si hubo algún fallo
for gate in "${GATES[@]}"; do
    if [[ "${RESULTS[$gate]:-SKIPPED}" != "PASS" ]]; then
        echo "CHECKPOINT 3 FAIL"
        exit 1
    fi
done

echo "CHECKPOINT 3 PASS"
exit 0
