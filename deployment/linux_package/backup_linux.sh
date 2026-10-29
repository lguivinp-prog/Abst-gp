#!/usr/bin/env bash
# =========================================================================
# ABST-GP V6 — Script de Generación de Respaldo en Servidor Linux (P19)
# =========================================================================
set -euo pipefail

ENV_FILE="${1:-.env.production}"
TIMESTAMP=$(date -u +"%Y%m%d_%H%M%S")
OUTPUT_TAR="/data/backups/abst_backup_${TIMESTAMP}.tar.enc"

if [ ! -f "$ENV_FILE" ]; then
    echo "[ERROR] Archivo de entorno $ENV_FILE no encontrado."
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.linux.yml"

echo "Iniciando respaldo consistente, firmado y cifrado..."
docker compose --project-directory "$REPO_ROOT" --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T api python /app/verification/dr/backup_lan_pg15.py backup \
    --uploads-dir /data/uploads \
    --output "$OUTPUT_TAR"

echo "[EXITO] Respaldo generado en $OUTPUT_TAR"
