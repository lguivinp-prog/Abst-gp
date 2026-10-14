#!/bin/sh
set -e

echo "Configuring pg_hba.conf for replication with SCRAM-SHA-256..."
if [ -f "$PGDATA/pg_hba.conf" ]; then
    if ! grep -q "host replication all all" "$PGDATA/pg_hba.conf"; then
        echo "host replication all all scram-sha-256" >> "$PGDATA/pg_hba.conf"
    fi
    if ! grep -q "host all all all" "$PGDATA/pg_hba.conf"; then
        echo "host all all all scram-sha-256" >> "$PGDATA/pg_hba.conf"
    fi
fi

# Validar que el directorio WAL archive sea accesible y escribible por postgres
ARCHIVE_DIR="/var/lib/postgresql/archive"
if [ ! -d "$ARCHIVE_DIR" ]; then
    echo "FATAL [init-replication.sh]: El directorio de archivo WAL '$ARCHIVE_DIR' no existe." >&2
    exit 1
fi

touch "$ARCHIVE_DIR/.probe_wal_write" && rm -f "$ARCHIVE_DIR/.probe_wal_write" || {
    echo "FATAL [init-replication.sh]: PostgreSQL carece de permisos de escritura en '$ARCHIVE_DIR'." >&2
    exit 1
}

echo "INFO [init-replication.sh]: WAL archive verificado con permisos de escritura para PostgreSQL."
