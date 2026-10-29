#!/usr/bin/env bash
# =========================================================================
# ABST-GP V6 — Script de Rollback Seguro en Servidor Linux (P19)
# =========================================================================
# Detiene el stack productivo de forma limpia SIN eliminar volumenes (-v prohibido)
# Preserva toda la data en disco y logs forenses.
set -euo pipefail

ENV_FILE="${1:-.env.production}"

echo "================================================================="
echo " EJECUTANDO ROLLBACK SEGURO DE CONTENEDORES LINUX"
echo " (Prohibido eliminar volumenes o respaldos)"
echo "================================================================="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.linux.yml"

if [ -f "$ENV_FILE" ]; then
    docker compose --project-directory "$REPO_ROOT" --env-file "$ENV_FILE" -f "$COMPOSE_FILE" stop
    docker compose --project-directory "$REPO_ROOT" --env-file "$ENV_FILE" -f "$COMPOSE_FILE" down
else
    docker compose --project-directory "$REPO_ROOT" -f "$COMPOSE_FILE" stop
    docker compose --project-directory "$REPO_ROOT" -f "$COMPOSE_FILE" down
fi

echo "[EXITO] Contenedores detenidos. Volúmenes y respaldos preservados intactos."
