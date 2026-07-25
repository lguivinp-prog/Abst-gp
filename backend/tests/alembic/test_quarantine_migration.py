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

def test_alembic_scenario_b_and_c():
    db_name = f"abst_alembic_b_{uuid.uuid4().hex}"
    temp_url = _verify_and_create_db(db_name)
    try:
        cfg = _get_alembic_config(temp_url)
        
        command.upgrade(cfg, "12fd022d7f66")
        
        engine = create_engine(temp_url)
        with engine.connect() as conn:
            conn.execute(text("INSERT INTO case_files (id, title, contract_type, status) VALUES (999, 'Test Case', 'Goods', 'OCR_COMPLETED')"))
            conn.execute(text("INSERT INTO uploaded_documents (id, case_id, document_type, stored_path, original_filename, mime_type, processing_status, ocr_engine_used) VALUES (9991, 999, 'requirement', 'req.pdf', 'req.pdf', 'application/pdf', 'completed', 'v1')"))
            conn.execute(text("INSERT INTO uploaded_documents (id, case_id, document_type, stored_path, original_filename, mime_type, processing_status, ocr_engine_used) VALUES (9992, 999, 'quotation', 'quo.pdf', 'quo.pdf', 'application/pdf', 'completed', 'v2')"))
            conn.execute(text("INSERT INTO parsed_sections (id, case_id, document_id, original_text, cleaned_text, normalized_text, extraction_metadata) VALUES (9991, 999, 9991, 'req', 'req', 'req', '{}')"))
            conn.execute(text("INSERT INTO parsed_sections (id, case_id, document_id, original_text, cleaned_text, normalized_text, extraction_metadata) VALUES (9992, 999, 9992, 'quo', 'quo', 'quo', '{}')"))
            
            req_item_id = str(uuid.uuid4())
            conn.execute(text(f"INSERT INTO requirement_items (id, parsed_section_id, item_type, content_text, is_approved) VALUES ('{req_item_id}', 9991, 'TECHNICAL', 'req', true)"))
            run_uuid = uuid.uuid4()
            conn.execute(text(f"INSERT INTO comparison_runs (id, case_id, requirement_doc_id, quotation_doc_id, status) VALUES ('{run_uuid}', 999, 9991, 9992, 'COMPLETED')"))
            conn.execute(text(f"INSERT INTO comparison_results (id, run_id, requirement_item_id, status, evaluation_method, confidence_score) VALUES ('{str(uuid.uuid4())}', '{run_uuid}', '{req_item_id}', 'PASS', 'EXACT_MATCH', 0.99)"))
            conn.execute(text("INSERT INTO users (username, password_hash, role, is_active) VALUES ('legacy_user', 'hash', 'OPERATOR', true)"))
            conn.commit()

        command.upgrade(cfg, "48cb7a717463")

        with engine.begin() as conn:
            conn.execute(text("UPDATE users SET tenant_resolution_status = 'QUARANTINED', is_active = false WHERE tenant_id IS NULL"))
            conn.execute(text("INSERT INTO user_tenant_quarantine (user_id, reason_code, status) SELECT id, 'MISSING_TENANT', 'QUARANTINED' FROM users WHERE tenant_id IS NULL"))

        command.upgrade(cfg, "head")

        with engine.connect() as conn:
            res = conn.execute(text("SELECT status FROM user_tenant_quarantine")).fetchall()
            assert len(res) == 1
            assert res[0][0] == 'QUARANTINED'

        command.downgrade(cfg, "12fd022d7f66")

        with engine.connect() as conn:
            res = conn.execute(text("SELECT username FROM users")).fetchall()
            assert len(res) == 1
            assert res[0][0] == 'legacy_user'
            
        engine.dispose()

    finally:
        _drop_db(db_name)
