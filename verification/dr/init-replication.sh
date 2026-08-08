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

# Ensure archive directory has postgres:postgres ownership and 0700 permissions
mkdir -p /var/lib/postgresql/archive
chown -R postgres:postgres /var/lib/postgresql/archive
chmod 0700 /var/lib/postgresql/archive

if [ -d /var/lib/postgresql/backup_vault ]; then
    chown -R postgres:postgres /var/lib/postgresql/backup_vault
    chmod 0700 /var/lib/postgresql/backup_vault
fi
