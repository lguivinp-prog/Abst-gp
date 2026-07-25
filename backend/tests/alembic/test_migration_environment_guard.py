import pytest
import unittest.mock as mock
from app.core.env_guard import validate_migration_environment, EnvGuardError

def test_guard_test_env_allowed():
    # test | test_db | coincidentes | permitido
    validate_migration_environment('test', 'postgresql://user:pass@localhost:5432/test_db', {})

def test_guard_test_env_abst_gp_rejected():
    # test | abst_gp | coincidentes | rechazado
    with pytest.raises(EnvGuardError, match="TEST environment cannot connect to 'abst_gp'"):
        validate_migration_environment('test', 'postgresql://user:pass@localhost:5432/abst_gp', {})

def test_guard_prod_env_missing_change_id():
    # production | abst_gp | Change ID ausente | rechazado
    with pytest.raises(EnvGuardError, match="MIGRATION_CHANGE_ID is required"):
        validate_migration_environment('production', 'postgresql://user:pass@localhost:5432/abst_gp', {
            'EXPECTED_DATABASE_HOST': 'localhost',
            'EXPECTED_DATABASE_PORT': '5432',
            'EXPECTED_DATABASE_NAME': 'abst_gp',
            'EXPECTED_ALEMBIC_TARGET': 'head',
        })

def test_guard_prod_env_wrong_db():
    # production | abst_gp | DB esperada incorrecta | rechazado
    with pytest.raises(EnvGuardError, match="Database mismatch. Expected 'wrong_db', got 'abst_gp'"):
        validate_migration_environment('production', 'postgresql://user:pass@localhost:5432/abst_gp', {
            'MIGRATION_CHANGE_ID': 'CHG-123',
            'EXPECTED_DATABASE_HOST': 'localhost',
            'EXPECTED_DATABASE_PORT': '5432',
            'EXPECTED_DATABASE_NAME': 'wrong_db',
            'EXPECTED_ALEMBIC_TARGET': 'head',
        })

def test_guard_prod_env_wrong_host():
    # production | abst_gp | host incorrecto | rechazado
    with pytest.raises(EnvGuardError, match="Host mismatch. Expected 'wrong_host', got 'localhost'"):
        validate_migration_environment('production', 'postgresql://user:pass@localhost:5432/abst_gp', {
            'MIGRATION_CHANGE_ID': 'CHG-123',
            'EXPECTED_DATABASE_HOST': 'wrong_host',
            'EXPECTED_DATABASE_PORT': '5432',
            'EXPECTED_DATABASE_NAME': 'abst_gp',
            'EXPECTED_ALEMBIC_TARGET': 'head',
        })

def test_guard_prod_env_wrong_port():
    # production | abst_gp | puerto incorrecto | rechazado
    with pytest.raises(EnvGuardError, match="Port mismatch. Expected '5433', got '5432'"):
        validate_migration_environment('production', 'postgresql://user:pass@localhost:5432/abst_gp', {
            'MIGRATION_CHANGE_ID': 'CHG-123',
            'EXPECTED_DATABASE_HOST': 'localhost',
            'EXPECTED_DATABASE_PORT': '5433',
            'EXPECTED_DATABASE_NAME': 'abst_gp',
            'EXPECTED_ALEMBIC_TARGET': 'head',
        })

def test_guard_prod_env_missing_target():
    # production | abst_gp | target incorrecto | rechazado
    with pytest.raises(EnvGuardError, match="EXPECTED_ALEMBIC_TARGET is required"):
        validate_migration_environment('production', 'postgresql://user:pass@localhost:5432/abst_gp', {
            'MIGRATION_CHANGE_ID': 'CHG-123',
            'EXPECTED_DATABASE_HOST': 'localhost',
            'EXPECTED_DATABASE_PORT': '5432',
            'EXPECTED_DATABASE_NAME': 'abst_gp',
        })

def test_guard_prod_env_all_match():
    # production | abst_gp | todo coincidente | validación lógica aprobada sin conexión
    validate_migration_environment('production', 'postgresql://user:pass@localhost:5432/abst_gp', {
        'MIGRATION_CHANGE_ID': 'CHG-123',
        'EXPECTED_DATABASE_HOST': 'localhost',
        'EXPECTED_DATABASE_PORT': '5432',
        'EXPECTED_DATABASE_NAME': 'abst_gp',
        'EXPECTED_ALEMBIC_TARGET': 'head',
    })

def test_guard_unknown_env():
    # desconocido | cualquier URL | cualquier valor | rechazado
    with pytest.raises(EnvGuardError, match="Unknown or unauthorized environment: unknown"):
        validate_migration_environment('unknown', 'postgresql://user:pass@localhost:5432/abst_gp', {})

@mock.patch('sqlalchemy.create_engine')
@mock.patch('sqlalchemy.engine_from_config')
def test_guard_does_not_create_engine(mock_engine_from_config, mock_create_engine):
    validate_migration_environment('production', 'postgresql://user:pass@localhost:5432/abst_gp', {
        'MIGRATION_CHANGE_ID': 'CHG-123',
        'EXPECTED_DATABASE_HOST': 'localhost',
        'EXPECTED_DATABASE_PORT': '5432',
        'EXPECTED_DATABASE_NAME': 'abst_gp',
        'EXPECTED_ALEMBIC_TARGET': 'head',
    })
    mock_create_engine.assert_not_called()
    mock_engine_from_config.assert_not_called()
