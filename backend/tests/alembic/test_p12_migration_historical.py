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

# 1. Base limpia, sin duplicados: verificar upgrade, downgrade, restricciones
def test_p12_migration_clean_db():
    db_name = f"abst_p12_clean_{uuid.uuid4().hex}"
    temp_url = _verify_and_create_db(db_name)
    try:
        cfg = _get_alembic_config(temp_url)
        # Migrar hasta la revisión previa a P12 (52a123bc45de)
        command.upgrade(cfg, "52a123bc45de")

        engine = create_engine(temp_url)
        with engine.connect() as conn:
            # Insertar tenant requerido por clave foránea
            conn.execute(text("""
                INSERT INTO tenants (id, name) VALUES ('mega_tenant', 'Mega Tenant') ON CONFLICT DO NOTHING;
            """))
            # Insertar datos limpios en la base previa
            conn.execute(text("""
                INSERT INTO case_files (title, status, contract_type, tenant_id, created_at)
                VALUES ('Expediente Limpio', 'COMPARING', 'bienes', 'mega_tenant', NOW() - INTERVAL '1 day');
            """))
            conn.execute(text("""
                INSERT INTO suppliers (ruc, business_name, tenant_id, created_at)
                VALUES ('20111222333', 'Proveedor Limpio SAC', 'mega_tenant', NOW());
            """))
            conn.execute(text("""
                INSERT INTO supplier_offers (case_id, supplier_id, status, evaluation_status, currency, price, created_at)
                VALUES (1, 1, 'SUBMITTED', 'PENDING', 'PEN', 15000, NOW());
            """))
            conn.execute(text("""
                INSERT INTO case_requirement_matrices (case_id, category, requirement_type, description, mandatory, status, created_at)
                VALUES (1, 'TECHNICAL', 'TECHNICAL', 'Requisito Limpio', true, 'VALIDATED', NOW());
            """))
            conn.execute(text("""
                INSERT INTO offer_evaluations (supplier_offer_id, requirement_id, status, explanation, created_at)
                VALUES (1, 1, 'PASSED', 'Evaluacion limpia inicial', NOW());
            """))
            conn.commit()

        # Ejecutar upgrade P12 (e7f891ab0123)
        command.upgrade(cfg, "e7f891ab0123")

        with engine.connect() as conn:
            # 1. Comprobar que se creó la tabla offer_requirement_evidences
            tbl_res = conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename = 'offer_requirement_evidences'")).fetchone()
            assert tbl_res is not None

            # 2. Comprobar que se creó la tabla archived_offer_evaluations
            arch_res = conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename = 'archived_offer_evaluations'")).fetchone()
            assert arch_res is not None

            # 3. Comprobar que se agregó la columna traceability_regime a case_files y se asignó HISTORICAL_P11
            regime = conn.execute(text("SELECT traceability_regime FROM case_files WHERE id = 1")).scalar_one()
            assert regime == "HISTORICAL_P11"

            # 4. Comprobar la restricción única uq_offer_evaluations_offer_req
            uq_res = conn.execute(text("""
                SELECT conname FROM pg_constraint
                WHERE conrelid = 'public.offer_evaluations'::regclass AND conname = 'uq_offer_evaluations_offer_req'
            """)).fetchone()
            assert uq_res is not None

        # Ejecutar downgrade de P12
        command.downgrade(cfg, "52a123bc45de")

        with engine.connect() as conn:
            # 1. La tabla offer_requirement_evidences debe haber sido eliminada
            tbl_down = conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename = 'offer_requirement_evidences'")).fetchone()
            assert tbl_down is None

            # 2. La tabla archived_offer_evaluations debe haber sido eliminada
            arch_down = conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename = 'archived_offer_evaluations'")).fetchone()
            assert arch_down is None

            # 3. La restricción única debe haber sido eliminada
            uq_down = conn.execute(text("""
                SELECT conname FROM pg_constraint
                WHERE conrelid = 'public.offer_evaluations'::regclass AND conname = 'uq_offer_evaluations_offer_req'
            """)).fetchone()
            assert uq_down is None

            # 4. La columna traceability_regime debe haber sido eliminada de case_files
            col_down = conn.execute(text("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'case_files' AND column_name = 'traceability_regime'
            """)).fetchone()
            assert col_down is None

        engine.dispose()
    finally:
        _drop_db(db_name)


# 2. Base con dos o más evaluaciones de una misma pareja oferta-requisito con estados y verificadores diferentes
def test_p12_migration_with_duplicate_evaluations_archived():
    db_name = f"abst_p12_dupes_{uuid.uuid4().hex}"
    temp_url = _verify_and_create_db(db_name)
    try:
        cfg = _get_alembic_config(temp_url)
        # Migrar hasta 52a123bc45de
        command.upgrade(cfg, "52a123bc45de")

        engine = create_engine(temp_url)
        with engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO tenants (id, name) VALUES ('mega_tenant', 'Mega Tenant') ON CONFLICT DO NOTHING;
            """))
            # Crear usuarios verificadores para probar datos históricos distintos
            conn.execute(text("""
                INSERT INTO users (id, username, password_hash, role, is_active, must_change_password, failed_login_count, tenant_id, tenant_resolution_status)
                VALUES 
                    (10, 'verificador_uno', 'hash1', 'OPERATOR', true, false, 0, 'mega_tenant', 'RESOLVED'),
                    (20, 'verificador_dos', 'hash2', 'SUPERVISOR', true, false, 0, 'mega_tenant', 'RESOLVED')
                ON CONFLICT (id) DO NOTHING;
            """))
            conn.execute(text("""
                INSERT INTO case_files (title, status, contract_type, tenant_id, created_at)
                VALUES ('Expediente con Duplicados', 'COMPARING', 'bienes', 'mega_tenant', NOW() - INTERVAL '2 days');
            """))
            conn.execute(text("""
                INSERT INTO suppliers (ruc, business_name, tenant_id, created_at)
                VALUES ('20444555666', 'Proveedor Concurrente SAC', 'mega_tenant', NOW());
            """))
            conn.execute(text("""
                INSERT INTO supplier_offers (case_id, supplier_id, status, evaluation_status, currency, price, created_at)
                VALUES (1, 1, 'SUBMITTED', 'PENDING', 'PEN', 20000, NOW());
            """))
            conn.execute(text("""
                INSERT INTO case_requirement_matrices (case_id, category, requirement_type, description, mandatory, status, created_at)
                VALUES (1, 'TECHNICAL', 'TECHNICAL', 'Requisito Duplicado', true, 'VALIDATED', NOW());
            """))

            # INSERTAR DOS EVALUACIONES CONTRADICTORIAS PARA LA MISMA PAREJA (oferta=1, requisito=1)
            # Fila 1: status='PASSED', confidence=0.85, validated_by=10
            conn.execute(text("""
                INSERT INTO offer_evaluations (supplier_offer_id, requirement_id, status, explanation, evaluation_confidence, validated_by, created_at)
                VALUES (1, 1, 'PASSED', 'Cumplimiento historico por operador 10', 0.85, 10, NOW() - INTERVAL '1 hour');
            """))
            # Fila 2: status='FAILED', confidence=0.99, validated_by=20
            conn.execute(text("""
                INSERT INTO offer_evaluations (supplier_offer_id, requirement_id, status, explanation, evaluation_confidence, validated_by, created_at)
                VALUES (1, 1, 'FAILED', 'Incumplimiento posterior por supervisor 20', 0.99, 20, NOW());
            """))
            conn.commit()

            # Confirmar que existen exactamente 2 evaluaciones antes de la migración
            count_before = conn.execute(text("SELECT count(*) FROM offer_evaluations WHERE supplier_offer_id = 1 AND requirement_id = 1")).scalar_one()
            assert count_before == 2

        # Ejecutar upgrade P12
        command.upgrade(cfg, "e7f891ab0123")

        with engine.connect() as conn:
            # 1. Comprobar que en la tabla activa offer_evaluations quedó exactamente 1 fila
            count_active = conn.execute(text("SELECT count(*) FROM offer_evaluations WHERE supplier_offer_id = 1 AND requirement_id = 1")).scalar_one()
            assert count_active == 1

            # La fila activa conservada es la más reciente (id mayor)
            active_row = conn.execute(text("SELECT status, validated_by, explanation FROM offer_evaluations WHERE supplier_offer_id = 1 AND requirement_id = 1")).fetchone()
            assert active_row[0] == "FAILED"
            assert active_row[1] == 20

            # 2. Comprobar que la fila duplicada histórica fue ARCHIVADA INTEGRAMENTE en archived_offer_evaluations
            archived_rows = conn.execute(text("""
                SELECT original_evaluation_id, supplier_offer_id, requirement_id, status, explanation, evaluation_confidence, validated_by, archival_reason
                FROM archived_offer_evaluations
            """)).fetchall()
            assert len(archived_rows) == 1
            archived = archived_rows[0]
            assert archived[1] == 1 # supplier_offer_id
            assert archived[2] == 1 # requirement_id
            assert archived[3] == "PASSED" # status histórico
            assert "operador 10" in archived[4] # explanation histórico
            assert archived[5] == 0.85 # confidence histórico
            assert archived[6] == 10 # validated_by histórico
            assert archived[7] == "MIGRATION_DUPLICATE_P12"

            # 3. Comprobar que se registró en audit_logs usando la columna real created_at (sin error de timestamp)
            audit_entry = conn.execute(text("""
                SELECT action, entity_type, status, created_at, details
                FROM audit_logs
                WHERE action = 'ARCHIVE_DUPLICATE_EVALUATION'
            """)).fetchone()
            assert audit_entry is not None
            assert audit_entry[0] == "ARCHIVE_DUPLICATE_EVALUATION"
            assert audit_entry[2] == "ARCHIVED"
            assert audit_entry[3] is not None # created_at poblado
            assert "operador 10" in audit_entry[4] # details contiene los metadatos

            # 4. Comprobar que la restricción única uq_offer_evaluations_offer_req está activa e impide insertar un nuevo duplicado
            with pytest.raises(Exception) as excinfo:
                conn.execute(text("""
                    INSERT INTO offer_evaluations (supplier_offer_id, requirement_id, status, explanation)
                    VALUES (1, 1, 'PASSED', 'Intento de duplicar oferta-requisito');
                """))
                conn.commit()
            assert "uq_offer_evaluations_offer_req" in str(excinfo.value) or "unique" in str(excinfo.value).lower()
            conn.rollback()

        # 5. Comprobar que el downgrade restaura el duplicado archivado a la tabla offer_evaluations
        command.downgrade(cfg, "52a123bc45de")

        with engine.connect() as conn:
            # Tras downgrade, ambas filas deben estar presentes en offer_evaluations
            count_restored = conn.execute(text("SELECT count(*) FROM offer_evaluations WHERE supplier_offer_id = 1 AND requirement_id = 1")).scalar_one()
            assert count_restored == 2

            # La tabla de archivo debe haber sido eliminada
            arch_table = conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename = 'archived_offer_evaluations'")).fetchone()
            assert arch_table is None

        engine.dispose()
    finally:
        _drop_db(db_name)


# 3. Prueba de colisión de identificadores durante downgrade y verificación de rollback
def test_p12_downgrade_aborts_on_id_collision():
    db_name = f"abst_p12_collision_{uuid.uuid4().hex}"
    temp_url = _verify_and_create_db(db_name)
    try:
        cfg = _get_alembic_config(temp_url)
        # Migrar hasta P12
        command.upgrade(cfg, "e7f891ab0123")

        engine = create_engine(temp_url)
        with engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO tenants (id, name) VALUES ('collision_tenant', 'Collision Tenant') ON CONFLICT DO NOTHING;
            """))
            conn.execute(text("""
                INSERT INTO case_files (id, title, status, contract_type, tenant_id, created_at)
                VALUES (100, 'Expediente Colision', 'COMPARING', 'bienes', 'collision_tenant', NOW());
            """))
            conn.execute(text("""
                INSERT INTO suppliers (id, ruc, business_name, tenant_id, created_at)
                VALUES (100, '20999888777', 'Proveedor Colision SAC', 'collision_tenant', NOW());
            """))
            conn.execute(text("""
                INSERT INTO supplier_offers (id, case_id, supplier_id, status, evaluation_status, currency, price, created_at)
                VALUES (100, 100, 100, 'SUBMITTED', 'PENDING', 'PEN', 50000, NOW());
            """))
            conn.execute(text("""
                INSERT INTO case_requirement_matrices (id, case_id, category, requirement_type, description, mandatory, status, created_at)
                VALUES (100, 100, 'TECHNICAL', 'TECHNICAL', 'Requisito Colision', true, 'VALIDATED', NOW());
            """))

            # Crear una fila activa en offer_evaluations con id = 500
            conn.execute(text("""
                INSERT INTO offer_evaluations (id, supplier_offer_id, requirement_id, status, explanation, created_at)
                VALUES (500, 100, 100, 'FAILED', 'Fila activa previa al downgrade', NOW());
            """))

            # Insertar en archived_offer_evaluations un registro con exactamente el MISMO original_evaluation_id = 500 (colisión)
            conn.execute(text("""
                INSERT INTO archived_offer_evaluations (original_evaluation_id, supplier_offer_id, requirement_id, status, explanation, archival_reason, archived_at)
                VALUES (500, 100, 100, 'PASSED', 'Fila archivada en colision', 'MIGRATION_DUPLICATE_P12', NOW());
            """))
            conn.commit()

        # Intentar ejecutar downgrade: DEBE FALLAR con excepción y abortar la transacción
        with pytest.raises(Exception) as excinfo:
            command.downgrade(cfg, "52a123bc45de")

        assert "colisiones de ID" in str(excinfo.value) or "Downgrade abortado" in str(excinfo.value)

        # Comprobar que archived_offer_evaluations sigue existiendo y conserva íntegramente la información
        with engine.connect() as conn:
            arch_table = conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename = 'archived_offer_evaluations'")).fetchone()
            assert arch_table is not None, "La tabla archived_offer_evaluations no debe ser eliminada tras abortar downgrade"

            arch_count = conn.execute(text("SELECT count(*) FROM archived_offer_evaluations WHERE original_evaluation_id = 500")).scalar_one()
            assert arch_count == 1, "El registro archivado debe conservarse intacto sin pérdida"

            active_row = conn.execute(text("SELECT status, explanation FROM offer_evaluations WHERE id = 500")).fetchone()
            assert active_row[0] == "FAILED", "La fila activa original debe conservarse intacta"

        engine.dispose()
    finally:
        _drop_db(db_name)
