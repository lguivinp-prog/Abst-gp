import os
import pytest
from sqlalchemy import create_engine
from tests.api.integration.schema_guard import assert_alembic_schema_current

def test_alembic_guard_validates_schema():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL is required")
        
    engine = create_engine(database_url)
    report = assert_alembic_schema_current(engine)
    
    assert report.expected_heads, "Expected heads should not be empty"
    assert report.current_heads == report.expected_heads, "Current heads do not match expected heads"
    assert not report.missing_tables, f"Missing critical tables: {report.missing_tables}"
    
    engine.dispose()
