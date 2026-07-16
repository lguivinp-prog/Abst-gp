import os
import pytest
from sqlalchemy import create_engine
from tests.api.integration.schema_guard import assert_alembic_schema_current, SchemaGuardError

@pytest.fixture(scope="session", autouse=True)
def integration_alembic_guard():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.fail("DATABASE_URL es obligatoria para las integraciones E2E.", pytrace=False)
        
    engine = create_engine(database_url, pool_pre_ping=True)
    
    try:
        assert_alembic_schema_current(engine)
    except SchemaGuardError as e:
        pytest.fail(f"Fallo de guardia Alembic: {str(e)}", pytrace=False)
    
    yield
    
    engine.dispose()
