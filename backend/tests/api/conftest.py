import os
import pytest
from sqlalchemy import create_engine
from app.models.domain import Base

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://abst_user:abst_password@db:5432/test_abst_gp")
engine = create_engine(DATABASE_URL)

@pytest.fixture(scope="session", autouse=True)
def setup_database_schema():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    # Keep it clean
    Base.metadata.drop_all(bind=engine)
