#!/usr/bin/env bash
# =========================================================================
# ABST-GP V6 — Script de Restauración Certificada en Linux (P19)
# =========================================================================
set -euo pipefail

BACKUP_TAR="${1:-/data/backups/pilot_backup_p19.tar.enc}"
ENV_FILE="${2:-.env.production}"

if [ ! -f "$ENV_FILE" ]; then
    echo "[ERROR] Archivo de entorno $ENV_FILE no encontrado. Configurelo antes de restaurar."
    exit 1
fi

if [ ! -f "$BACKUP_TAR" ]; then
    echo "[ERROR] Archivo de respaldo $BACKUP_TAR no encontrado."
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.linux.yml"

echo "================================================================="
echo " ABST-GP V6 — INICIANDO RESTAURACIÓN CONTROLADA EN LINUX"
echo "================================================================="
echo " Respaldo:   $BACKUP_TAR"
echo " Entorno:    $ENV_FILE"
echo " Fecha:      $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
echo "-----------------------------------------------------------------"

# 1. Asegurar que los servicios DB y Redis esten saludables
echo "[1/4] Levantando y verificando servicios de base de datos..."
docker compose --project-directory "$REPO_ROOT" --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d db redis api

echo "[2/4] Esperando disponibilidad de PostgreSQL..."
until docker compose --project-directory "$REPO_ROOT" --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T db pg_isready -U abst_prod_admin; do
    sleep 2
done

# 2. Generar token y marcador de propiedad efimero en la BD destino
RUN_TOKEN=$(openssl rand -hex 4)
MARKER_ID="marker_prod_${RUN_TOKEN}"

echo "[3/4] Registrando marcador efimero de propiedad ($MARKER_ID)..."
docker compose --project-directory "$REPO_ROOT" --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T db psql -U abst_prod_admin -d abst_gp_lan -c "
CREATE TABLE IF NOT EXISTS _dr_test_ownership_marker (marker_id VARCHAR(64) PRIMARY KEY);
DELETE FROM _dr_test_ownership_marker;
INSERT INTO _dr_test_ownership_marker (marker_id) VALUES ('$MARKER_ID');
"

# 3. Ejecutar restauracion autenticada utilizando la herramienta reproducible montada
echo "[4/4] Ejecutando restauracion integral autenticada..."
docker compose --project-directory "$REPO_ROOT" --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T api python /app/verification/dr/backup_lan_pg15.py restore \
    --backup-file "$BACKUP_TAR" \
    --target-uploads /data/uploads \
    --target-db-url "postgresql+psycopg2://abst_prod_admin:\${POSTGRES_PASSWORD}@db:5432/abst_gp_lan" \
    --source-db-url "postgresql://db:5432/abst_gp_pilot" \
    --expected-marker "$MARKER_ID"

echo "================================================================="
echo " [EXITO] RESTAURACIÓN LINUX COMPLETADA SATISFACTORIAMENTE"
echo " Proceda a iniciar el resto de servicios con:"
echo " docker compose --project-directory $REPO_ROOT --env-file $ENV_FILE -f $COMPOSE_FILE up -d"
echo "================================================================="
