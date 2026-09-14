import pytest
import uuid
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from sqlalchemy import text, create_engine
from alembic.config import Config
from alembic import command
import os
from urllib.parse import urlparse

db_url = os.environ.get("DATABASE_URL", "postgresql://test_user:test_password@localhost:15432/test_db")
parsed = urlparse(db_url)
ADMIN_DB_URL = f"postgresql://{parsed.username}:{parsed.password}@{parsed.hostname}:{parsed.port}/postgres"

def _verify_and_create_db(db_name: str) -> str:
    conn = psycopg2.connect(ADMIN_DB_URL)
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()

    cur.execute("SELECT current_database(), current_user, inet_server_addr(), inet_server_port()")
    db, user, addr, port = cur.fetchone()

    assert db == "postgres", f"Admin connection should point to postgres, got {db}"
    assert "abst_gp" not in db_name, "Cannot use abst_gp"
    assert user == parsed.username
    assert port == 5432

    cur.execute(f'CREATE DATABASE "{db_name}"')
    cur.close()
    conn.close()

    return f"postgresql://{parsed.username}:{parsed.password}@{parsed.hostname}:{parsed.port}/{db_name}"

def _drop_db(db_name: str):
    conn = psycopg2.connect(ADMIN_DB_URL)
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()

    cur.execute(f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{db_name}' AND pid <> pg_backend_pid()")
    cur.execute(f'DROP DATABASE "{db_name}"')
    cur.close()
    conn.close()

def _get_alembic_config(temp_url: str):
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", temp_url)
    return alembic_cfg

def test_alembic_scenario_a():
    db_name = f"abst_alembic_a_{uuid.uuid4().hex}"
    temp_url = _verify_and_create_db(db_name)
    try:
        cfg = _get_alembic_config(temp_url)
        command.upgrade(cfg, "head")

        engine = create_engine(temp_url)
        with engine.connect() as conn:
            res = conn.execute(text("SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid = 'public.users'::regclass ORDER BY conname")).fetchall()
            constraints = {r[0]: r[1] for r in res}
            assert "chk_users_tenant_resolution" in constraints

            res_idx = conn.execute(text("SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = 'public' AND tablename = 'users' ORDER BY indexname")).fetchall()
            indexes = {r[0]: r[1] for r in res_idx}
            assert "ix_users_admin_singleton" not in indexes
            assert "ix_users_username" in indexes
        engine.dispose()
    finally:
        _drop_db(db_name)
