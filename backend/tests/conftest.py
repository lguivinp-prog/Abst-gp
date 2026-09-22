import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, scoped_session
import redis
import os
from app.models.base import Base
from alembic.config import Config
from alembic import command
from app.models.domain import Tenant, RolloutTenantAssignment, SystemSettings

import sys

def ensure_safe_test_db(conn):
    if "sqlite" in str(conn.engine.url): return
    db_name = conn.execute(text("SELECT current_database()")).scalar()
    if not db_name:
        pytest.exit("FATAL: Could not determine database name. Aborting test.")

    db_name = db_name.lower()
    if "abst_gp" in db_name or "production" in db_name:
        pytest.exit(f"FATAL: Database name '{db_name}' is protected. Tests cannot run against development/production targets.")

    if "test" not in db_name:
        pytest.exit(f"FATAL: Database name '{db_name}' does not look like a test database (must contain 'test').")

    app_env = os.environ.get("APP_ENV")
    if app_env != "test":
        pytest.exit(f"FATAL: APP_ENV is '{app_env}', but must be 'test' for destructive operations.")

# Configurar namespace y db exclusivas para testing
TEST_DATABASE_URL = os.environ.get("DATABASE_URL")
if not TEST_DATABASE_URL:
    print("FATAL: DATABASE_URL not set in environment.")
    sys.exit(1)
if os.environ.get("APP_ENV") != "test":
    print("FATAL: APP_ENV is not 'test'. Refusing to run tests against potentially real DB.")
    sys.exit(1)
TEST_REDIS_URL = os.getenv("TEST_REDIS_URL", "redis://abst_redis:6379/1") # Use DB 1 for testing

engine = create_engine(TEST_DATABASE_URL)
TestingSessionLocal = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))

@pytest.fixture(scope="session", autouse=True)
def setup_test_db_schema():
    """Ejecuta alembic upgrade head una vez por sesión de tests"""
    with engine.connect() as conn:
        ensure_safe_test_db(conn)
        db_name = "sqlite" if "sqlite" in str(conn.engine.url) else conn.execute(text("SELECT current_database()")).scalar()
        print(f"\n--- Pytest running against isolated DB: {db_name} ---")

    # NO_USE_METADATA_CREATE_ALL
    alembic_cfg = Config("alembic.ini")
    # Forzamos la url en alembic config
    alembic_cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    
    # Podríamos hacer downgrade base y luego upgrade head si se quiere reset puro,
    command.upgrade(alembic_cfg, "head")
    
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO tenants (id, name, created_at) VALUES ('mega_tenant', 'Mega Tenant', NOW()) ON CONFLICT DO NOTHING"))
        conn.execute(text("INSERT INTO rollout_tenant_assignments (tenant_id, routing_mode, assignment_version) VALUES ('mega_tenant', 'FORCE_LEGACY', 'v1') ON CONFLICT DO NOTHING"))
        conn.execute(text("""
            INSERT INTO users (id, username, password_hash, role, is_active, must_change_password, tenant_id, tenant_resolution_status, failed_login_count)
            VALUES 
            (1, 'operator', 'mock', 'OPERATOR', true, false, 'mega_tenant', 'RESOLVED', 0),
            (2, 'admin', 'mock', 'ADMIN', true, false, 'mega_tenant', 'RESOLVED', 0)
            ON CONFLICT DO NOTHING
        """))
        conn.execute(text("SELECT setval('users_id_seq', (SELECT MAX(id) FROM users))"))
        
    yield

@pytest.fixture(scope="function")
def db_session():
    """Provee una sesion limpia para cada test y limpia las tablas transaccionales"""
    tables = [
        "users", "audit_logs", "case_files", "uploaded_documents", 
        "parsed_sections", "quotation_extractions", "comparison_runs", 
        "comparison_results", "requirement_items", "generated_outputs", 
        "processing_jobs", "processing_metrics", "worker_heartbeats"
    ]
    
    with engine.begin() as conn:
        ensure_safe_test_db(conn)
        conn.execute(text(f"TRUNCATE TABLE {', '.join(tables)} RESTART IDENTITY CASCADE"))
        conn.execute(text("INSERT INTO tenants (id, name, created_at) VALUES ('mega_tenant', 'Mega Tenant', NOW()) ON CONFLICT DO NOTHING"))
        conn.execute(text("INSERT INTO rollout_tenant_assignments (tenant_id, routing_mode, assignment_version) VALUES ('mega_tenant', 'FORCE_LEGACY', 'v1') ON CONFLICT DO NOTHING"))
        conn.execute(text("""
            INSERT INTO users (id, username, password_hash, role, is_active, must_change_password, tenant_id, tenant_resolution_status, failed_login_count)
            VALUES 
            (1, 'operator', 'mock', 'OPERATOR', true, false, 'mega_tenant', 'RESOLVED', 0),
            (2, 'admin', 'mock', 'ADMIN', true, false, 'mega_tenant', 'RESOLVED', 0)
            ON CONFLICT DO NOTHING
        """))
        conn.execute(text("SELECT setval('users_id_seq', (SELECT MAX(id) FROM users))"))

    session = TestingSessionLocal()
    
    yield session
    
    session.rollback()
    session.close()
    
    # Limpiar overrides de dependencias
    from app.main import app
    app.dependency_overrides.clear()
    
    # Truncate tables between tests (preservando esquema y tablas de config)
    with engine.begin() as conn:
        ensure_safe_test_db(conn)
        # RESTART IDENTITY asegura que las IDs vuelvan a 1. CASCADE limpia dependencias.
        conn.execute(text(f"TRUNCATE TABLE {', '.join(tables)} RESTART IDENTITY CASCADE"))
        
        # Insert mock users used by authz override
        conn.execute(text("""
            INSERT INTO users (id, username, password_hash, role, is_active, must_change_password, tenant_id, tenant_resolution_status, failed_login_count)
            VALUES 
            (1, 'operator', 'mock', 'OPERATOR', true, false, 'mega_tenant', 'RESOLVED', 0),
            (2, 'admin', 'mock', 'ADMIN', true, false, 'mega_tenant', 'RESOLVED', 0)
            ON CONFLICT DO NOTHING
        """))
        conn.execute(text("SELECT setval('users_id_seq', (SELECT MAX(id) FROM users))"))

@pytest.fixture(scope="function")
def setup_mega_tenant(db_session):
    """Fixture para sembrar mega_tenant de forma determinista para los tests"""
    # La migración ya inserta mega_tenant en 'tenants' y system_settings en (1,0)
    # Por si se limpia, nos aseguramos
    tenant = db_session.query(Tenant).filter_by(id="mega_tenant").first()
    if not tenant:
        tenant = Tenant(id="mega_tenant", name="Mega Tenant")
        db_session.add(tenant)
        
    assignment = db_session.query(RolloutTenantAssignment).filter_by(tenant_id="mega_tenant").first()
    if not assignment:
        assignment = RolloutTenantAssignment(
            tenant_id="mega_tenant",
            assignment_version="v1",
            routing_mode="FORCE_LEGACY"
        )
        db_session.add(assignment)
        
    db_session.commit()
    return tenant

@pytest.fixture(scope="function")
def redis_client():
    """Limpia el namespace Redis de pruebas antes y después de cada test"""
    client = redis.Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    client.flushdb()
    yield client
    client.flushdb()

@pytest.fixture(scope="function")
def client(db_session):
    from app.main import app
    from fastapi.testclient import TestClient
    from app.api.auth import get_current_active_user, get_current_user
    from app.models.domain import User

    def override_get_current_active_user():
        return User(id=1, username="operator", role="OPERATOR", is_active=True, must_change_password=False, tenant_id="mega_tenant")
    
    app.dependency_overrides[get_current_active_user] = override_get_current_active_user
    app.dependency_overrides[get_current_user] = override_get_current_active_user
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_current_active_user, None)
    app.dependency_overrides.pop(get_current_user, None)

@pytest.fixture(scope="function")
def admin_client(db_session):
    from app.main import app
    from fastapi.testclient import TestClient
    from app.api.auth import get_current_active_user, get_current_user
    from app.models.domain import User

    def override_get_current_active_user_admin():
        return User(id=2, username="admin", role="ADMIN", is_active=True, must_change_password=False, tenant_id="mega_tenant")
    
    app.dependency_overrides[get_current_active_user] = override_get_current_active_user_admin
    app.dependency_overrides[get_current_user] = override_get_current_active_user_admin
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_current_active_user, None)
    app.dependency_overrides.pop(get_current_user, None)

