import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.domain import Base

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://abst_user:abst_password@db:5432/test_abst_gp")
engine = create_engine(DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="session", autouse=True)
def setup_database_schema():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    # No drop_all here because alembic might have populated stuff, we just let the DB persist,
    # but the transaction rollback per test keeps data clean.

@pytest.fixture(scope="function")
def db_session():
    connection = engine.connect()
    transaction = connection.begin()
    
    # join_transaction_mode="create_savepoint" enables nested savepoints when session.commit() is called
    session = TestingSessionLocal(bind=connection, join_transaction_mode="create_savepoint")
    
    yield session
    
    session.close()
    transaction.rollback()
    connection.close()
