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

function run_compose_timed() {
    local max_time="$1"
    shift
    if command -v timeout >/dev/null 2>&1; then
        timeout --kill-after=30s "$max_time" docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" "$@"
    else
        run_compose "$@"
    fi
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

# E.2 BOOTSTRAP SEED
echo "[E.2] Bootstrap Base Data..."
run_compose run --rm backend-test python scripts/seed_base.py > "$ARTIFACTS_DIR/seed.log" 2>&1 || { RESULTS["SEED"]="FAIL"; exit 1; }
RESULTS["SEED"]="PASS"

# (Seed E2E has been moved down closer to Browser E2E)

# F. BACKEND SUITE
echo "[F] Backend Suite Completa..."
run_compose_timed 25m run --rm backend-test python -m pytest tests/ -v --ignore=tests/e2e > "$ARTIFACTS_DIR/pytest-full.log" 2>&1 || { RESULTS["SUITE_BACKEND"]="FAIL"; exit 1; }
RESULTS["SUITE_BACKEND"]="PASS"

# G. CONCURRENCIA
echo "[G] Prueba Real de Concurrencia..."
run_compose_timed 5m run --rm backend-test python -m pytest tests/api/integration/test_comparison_concurrency.py -v > "$ARTIFACTS_DIR/concurrency.log" 2>&1 || { RESULTS["CONCURRENCY"]="FAIL"; exit 1; }
RESULTS["CONCURRENCY"]="PASS"

# H. ROLLBACK
echo "[H] Prueba Real de Rollback..."
run_compose_timed 5m run --rm backend-test python -m pytest tests/api/integration/test_comparison_rollback.py -v > "$ARTIFACTS_DIR/rollback.log" 2>&1 || { RESULTS["ROLLBACK"]="FAIL"; exit 1; }
RESULTS["ROLLBACK"]="PASS"

# I. DOCUMENTAL SECURITY
echo "[I] Gate Documental (Seguridad)..."
run_compose_timed 5m run --rm backend-test python -m pytest tests/e2e/test_documental_security.py -v > "$ARTIFACTS_DIR/documental.log" 2>&1 || { RESULTS["DOCUMENTAL"]="FAIL"; exit 1; }
RESULTS["DOCUMENTAL"]="PASS"

# J. LEGACY V5 INFRASTRUCTURE PIPELINE
echo "[J] LEGACY_V5_INFRASTRUCTURE_PIPELINE..."
run_compose up -d backend-app worker-test
echo "Esperando a backend y worker..."
sleep 15
run_compose_timed 10m run --rm backend-test python -m pytest tests/e2e/test_full_document_pipeline.py -v > "$ARTIFACTS_DIR/legacy_e2e.log" 2>&1 || { RESULTS["LEGACY_V5_INFRASTRUCTURE_PIPELINE"]="FAIL"; exit 1; }
if grep -q "1 skipped" "$ARTIFACTS_DIR/legacy_e2e.log" || ! grep -q "passed" "$ARTIFACTS_DIR/legacy_e2e.log"; then
    echo "LEGACY API E2E Zero-Test Defect detected (Skipped or no passes)."
    RESULTS["LEGACY_V5_INFRASTRUCTURE_PIPELINE"]="FAIL"
    exit 1
fi
RESULTS["LEGACY_V5_INFRASTRUCTURE_PIPELINE"]="PASS"

# --- ISOLATION BOUNDARY ---
echo "[J.1] ISOLATION BOUNDARY: Limpiando Redis y reiniciando worker deterministicamente..."
run_compose stop worker-test backend-app
run_compose exec -T redis-test redis-cli -n 1 FLUSHDB

echo "Terminando sesiones residuales de test_db..."
run_compose exec -T db-test psql -U test_user -d test_db -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'test_db' AND pid <> pg_backend_pid();"

echo "Esperando quiescence de test_db..."
DB_READY=0
for i in {1..30}; do
    ACTIVE_SESSIONS=$(run_compose exec -T db-test psql -U test_user -d test_db -t -A -c "SELECT count(*) FROM pg_stat_activity WHERE datname = 'test_db' AND pid <> pg_backend_pid();")
    if [ "$ACTIVE_SESSIONS" -eq 0 ]; then
        DB_READY=1
        break
    fi
    sleep 2
done

if [ "$DB_READY" -eq 0 ]; then
    echo "ERROR: test_db no alcanzó quiescence."
    RESULTS["NATIVE_V6_API_E2E"]="FAIL"
    exit 1
fi

run_compose start backend-app worker-test

echo "Esperando readiness del backend..."
BACKEND_READY=0
for i in {1..30}; do
    if run_compose exec -T backend-app curl -s http://localhost:8000/health | grep -q "ok"; then
        BACKEND_READY=1
        break
    fi
    sleep 2
done

if [ "$BACKEND_READY" -eq 0 ]; then
    echo "ERROR: Backend no respondió a tiempo."
    RESULTS["NATIVE_V6_API_E2E"]="FAIL"
    exit 1
fi
echo "Backend está listo."

echo "Esperando readiness del worker..."
WORKER_READY=0
for i in {1..30}; do
    if run_compose exec -T worker-test rq info -u redis://redis-test:6379/1 | grep -q "1 workers,"; then
        WORKER_READY=1
        break
    fi
    sleep 2
done

if [ "$WORKER_READY" -eq 0 ]; then
    echo "ERROR: Worker no inició o no se registró a tiempo."
    RESULTS["NATIVE_V6_API_E2E"]="FAIL"
    exit 1
fi
echo "Worker está listo y registrado."

# J.2 NATIVE V6 API E2E
echo "[J.2] NATIVE_V6_API_E2E..."
run_compose_timed 10m run --rm backend-test python -m pytest tests/e2e/test_v6_full_document_pipeline.py -v > "$ARTIFACTS_DIR/native_v6_e2e.log" 2>&1 || { RESULTS["NATIVE_V6_API_E2E"]="FAIL"; exit 1; }
if grep -q "1 skipped" "$ARTIFACTS_DIR/native_v6_e2e.log" || ! grep -q "passed" "$ARTIFACTS_DIR/native_v6_e2e.log"; then
    echo "NATIVE V6 API E2E Zero-Test Defect detected (Skipped, no passes)."
    RESULTS["NATIVE_V6_API_E2E"]="FAIL"
    exit 1
fi
RESULTS["NATIVE_V6_API_E2E"]="PASS"

# K. BROWSER E2E
echo "[K] Browser E2E..."
# Re-seed E2E data after Backend Suite may have truncated and corrupted the DB
echo "[K.1] Bootstrap E2E Data para Browser..."
run_compose run --rm -e ALLOW_E2E_SEED=true backend-test python scripts/seed_e2e.py > "$ARTIFACTS_DIR/seed_e2e.log" 2>&1 || { RESULTS["SEED_E2E"]="FAIL"; exit 1; }
RESULTS["SEED_E2E"]="PASS"

# Frontend ya debería estar corriendo en background para ser probado
run_compose up -d frontend-test
echo "Instalando Playwright dependencias en test container y ejecutando pruebas..."
run_compose_timed 15m run --rm browser-test sh -c "npm install && npx playwright install --with-deps chromium && npm run test" > "$ARTIFACTS_DIR/browser_e2e.log" 2>&1 || { RESULTS["BROWSER_E2E"]="FAIL"; exit 1; }
RESULTS["BROWSER_E2E"]="PASS"

# L. REPORTE
echo "--- GENERANDO REPORTE MATRIZ ---"
REPORT_FILE="$ARTIFACTS_DIR/gate-summary.md"
echo "# Resumen del Gate V5.2.1 Checkpoint 3" > "$REPORT_FILE"
echo "" >> "$REPORT_FILE"
echo "| Gate | Estado |" >> "$REPORT_FILE"
echo "|------|--------|" >> "$REPORT_FILE"
GATES=("PREFLIGHT" "BUILD" "FRONTEND" "DEPENDENCIAS" "ALEMBIC" "SEED" "SEED_E2E" "SUITE_BACKEND" "CONCURRENCY" "ROLLBACK" "DOCUMENTAL" "LEGACY_V5_INFRASTRUCTURE_PIPELINE" "NATIVE_V6_API_E2E" "BROWSER_E2E")
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
