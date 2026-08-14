#!/bin/bash
set -e

echo "Destroying db volume..."
docker-compose stop db
docker-compose rm -f db
docker volume rm abst-v4_9-remediation-clean_pgdata || true

echo "Starting db..."
docker-compose up -d db

echo "Waiting for db to be ready..."
sleep 10
docker exec abst_db pg_isready -U abst_user -d abst_gp
while [ $? -ne 0 ]; do
    sleep 2
    docker exec abst_db pg_isready -U abst_user -d abst_gp
done

echo "Running migrations..."
docker exec -e APP_ENV=production -e MIGRATION_CHANGE_ID=123 -e EXPECTED_DATABASE_HOST=db -e EXPECTED_DATABASE_PORT=5432 -e EXPECTED_DATABASE_NAME=abst_gp -e EXPECTED_ALEMBIC_TARGET=head abst_api alembic upgrade head

echo "Seeding users..."
docker exec abst_api python scripts/seed_dev_users.py

echo "Done!"
