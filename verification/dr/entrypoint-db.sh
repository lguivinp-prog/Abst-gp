#!/bin/sh
set -e

# ==============================================================================
# Entrypoint wrapper para PostgreSQL 16 DR (Fase P10)
# Se ejecuta inicialmente como root (UID 0) para configurar y verificar
# los permisos de los volúmenes montados antes de delegar a docker-entrypoint.sh
# ==============================================================================

ARCHIVE_DIR="/var/lib/postgresql/archive"
VAULT_DIR="/var/lib/postgresql/backup_vault"

# 1. Asegurar existencia de directorios requeridos para WAL archiving y backup vault
mkdir -p "$ARCHIVE_DIR" "$VAULT_DIR"

# 2. Configurar propiedad postgres:postgres y permisos estrictos 0700
chown -R postgres:postgres "$ARCHIVE_DIR" "$VAULT_DIR"
chmod 0700 "$ARCHIVE_DIR" "$VAULT_DIR"

# 3. Validar permisos efectivos y propiedad
for dir in "$ARCHIVE_DIR" "$VAULT_DIR"; do
    if [ ! -d "$dir" ]; then
        echo "FATAL [entrypoint-db.sh]: El directorio $dir no existe." >&2
        exit 1
    fi
done

# 4. Comprobación explícita de escritura para el usuario postgres en el directorio WAL
su-exec postgres touch "$ARCHIVE_DIR/.wal_write_test" && su-exec postgres rm -f "$ARCHIVE_DIR/.wal_write_test" || {
    echo "FATAL [entrypoint-db.sh]: El usuario 'postgres' carece de permisos de escritura en $ARCHIVE_DIR." >&2
    exit 1
}

# 5. Comprobación explícita de escritura para el usuario postgres en el backup vault
su-exec postgres touch "$VAULT_DIR/.vault_write_test" && su-exec postgres rm -f "$VAULT_DIR/.vault_write_test" || {
    echo "FATAL [entrypoint-db.sh]: El usuario 'postgres' carece de permisos de escritura en $VAULT_DIR." >&2
    exit 1
}

echo "INFO [entrypoint-db.sh]: Permisos de almacenamiento DR verificados exitosamente (postgres:postgres 0700)."

# 6. Delegar la ejecución al entrypoint canónico de PostgreSQL pasando los argumentos originales
exec docker-entrypoint.sh "$@"
