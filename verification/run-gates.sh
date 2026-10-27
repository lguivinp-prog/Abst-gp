#!/bin/bash
set -Eeuo pipefail

export PROJECT_NAME="${PROJECT_NAME:-abst_p14_validation}"
export COMPOSE_FILE="verification/docker-compose.test.yml"
KEEP_ENV="${KEEP_ENV:-0}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
ARTIFACTS_DIR="artifacts/verification/p14/${TIMESTAMP}"

mkdir -p "$ARTIFACTS_DIR"
cd "$(dirname "$0")/.."

echo "============================================="
echo "INICIANDO CERTIFICACIÓN CANÓNICA P14 - 14/14 GATES"
echo "============================================="

if [[ "$PROJECT_NAME" != "abst_p14_validation" ]]; then
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
    if [[ "$PROJECT_NAME" == "abst_p14_validation" ]]; then
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
BASE_COMMIT="${BASE_COMMIT:-caa135c25392330b483167d5d552c51dc398a905}"
# Calcular Candidate Tree SHA pre-gates de forma estricta
TMP_PRE_IDX=$(mktemp 2>/dev/null || echo "/tmp/git_pre_idx_$$")
TMP_PRE_PATCH=$(mktemp 2>/dev/null || echo "/tmp/git_pre_patch_$$.patch")
git diff "$BASE_COMMIT" --binary --output="$TMP_PRE_PATCH"
GIT_INDEX_FILE="$TMP_PRE_IDX" git read-tree "$BASE_COMMIT"
GIT_INDEX_FILE="$TMP_PRE_IDX" git apply --cached --binary --whitespace=nowarn "$TMP_PRE_PATCH"
TREE_SHA_BEFORE=$(GIT_INDEX_FILE="$TMP_PRE_IDX" git write-tree)
rm -f "$TMP_PRE_IDX" "$TMP_PRE_PATCH" 2>/dev/null || true
echo "Candidate Tree SHA (Pre-Gates): ${TREE_SHA_BEFORE}"

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
run_compose stop worker-test backend-app 2>/dev/null || true
run_compose_timed 25m run --rm backend-test python -m pytest tests/ -v --ignore=tests/e2e > "$ARTIFACTS_DIR/pytest-full.log" 2>&1 || { RESULTS["SUITE_BACKEND"]="FAIL"; exit 1; }
RESULTS["SUITE_BACKEND"]="PASS"

# G. CONCURRENCIA
echo "[G] Prueba Real de Concurrencia (Legacy + P13)..."
run_compose_timed 5m run --rm backend-test python -m pytest tests/api/integration/test_comparison_concurrency.py tests/api/v6/test_p13_concurrency_idempotency.py -v > "$ARTIFACTS_DIR/concurrency.log" 2>&1 || { RESULTS["CONCURRENCY"]="FAIL"; exit 1; }
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
echo "[J.1] ISOLATION BOUNDARY: Reiniciando worker y backend ordenadamente..."
run_compose stop worker-test backend-app
run_compose start backend-app worker-test
sleep 5

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

run_compose up -d frontend-test
echo "Ejecutando suite Playwright Chromium completa..."
run_compose_timed 15m run --rm browser-test sh -c "npx playwright test --output=/tmp/test-results --reporter=line" > "$ARTIFACTS_DIR/browser_e2e.log" 2>&1 || { RESULTS["BROWSER_E2E"]="FAIL"; exit 1; }
RESULTS["BROWSER_E2E"]="PASS"

# L. REPORTE
echo "--- GENERANDO REPORTE MATRIZ ---"
REPORT_FILE="$ARTIFACTS_DIR/gate-summary.md"
BASE_COMMIT="${BASE_COMMIT:-caa135c25392330b483167d5d552c51dc398a905}"
# 1. B3: Deteccion de archivos no rastreados (untracked)
UNTRACKED=$(git ls-files --others --exclude-standard 2>/dev/null || true)
UNTRACKED_OFFENDERS=""
for f in $UNTRACKED; do
    case "$f" in
        artifacts/*|*.zip|.git/*|test_dummy.db) ;;
        *) UNTRACKED_OFFENDERS="${UNTRACKED_OFFENDERS} $f" ;;
    esac
done
if [ -n "$UNTRACKED_OFFENDERS" ]; then
    echo "ERROR B3: Archivos untracked detectados que serian omitidos silenciosamente: $UNTRACKED_OFFENDERS" >&2
    exit 1
fi

TMP_INDEX=$(mktemp 2>/dev/null || echo "/tmp/git_idx_$$")
TMP_PATCH=$(mktemp 2>/dev/null || echo "/tmp/git_patch_$$.patch")
PREV_INDEX="${GIT_INDEX_FILE:-}"
git diff "$BASE_COMMIT" --binary --output="$TMP_PATCH" || { echo "ERROR B3: Fallo en git diff" >&2; exit 1; }
PATCH_SHA256=$(sha256sum "$TMP_PATCH" | cut -d' ' -f1)
export GIT_INDEX_FILE="$TMP_INDEX"
git read-tree "$BASE_COMMIT" || { echo "ERROR B3: Fallo en git read-tree" >&2; exit 1; }
git apply --cached --binary --whitespace=nowarn "$TMP_PATCH" || { echo "ERROR B3: Fallo en git apply" >&2; exit 1; }
TREE_SHA=$(git write-tree) || { echo "ERROR B3: Fallo en git write-tree" >&2; exit 1; }
git diff --quiet "$TREE_SHA" || {
    echo "ERROR B3: Arbol reconstruido no coincide exactamente con el candidato de trabajo" >&2
    exit 1
}
if [ -n "$TREE_SHA_BEFORE" ] && [ "$TREE_SHA" != "$TREE_SHA_BEFORE" ]; then
    echo "ERROR B4: Candidate Tree SHA difiere antes y despues de gates ($TREE_SHA_BEFORE != $TREE_SHA)" >&2
    exit 1
fi
rm -f "$TMP_INDEX" "$TMP_PATCH" 2>/dev/null || true
if [ -n "$PREV_INDEX" ]; then
    export GIT_INDEX_FILE="$PREV_INDEX"
else
    unset GIT_INDEX_FILE
fi
HEAD_SHA=$(git rev-parse HEAD 2>/dev/null || echo "UNKNOWN")
BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "UNKNOWN")
echo "# Resumen de Certificación Canónica P14 (14/14 Release Gates)" > "$REPORT_FILE"
echo "" >> "$REPORT_FILE"
echo "**Run ID:** ${TIMESTAMP}" >> "$REPORT_FILE"
echo "**Base Commit:** ${BASE_COMMIT}" >> "$REPORT_FILE"
echo "**Candidate Tree SHA:** ${TREE_SHA}" >> "$REPORT_FILE"
echo "**Candidate Patch SHA-256:** ${PATCH_SHA256}" >> "$REPORT_FILE"
echo "**Worktree HEAD:** ${HEAD_SHA}" >> "$REPORT_FILE"
echo "**Worktree Branch:** ${BRANCH}" >> "$REPORT_FILE"
echo "**Artifacts Dir:** ${ARTIFACTS_DIR}" >> "$REPORT_FILE"
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
        echo "RELEASE CERTIFICATION P14 FAIL"
        exit 1
    fi
done

echo "RELEASE CERTIFICATION P14 PASS (14/14)"
exit 0
