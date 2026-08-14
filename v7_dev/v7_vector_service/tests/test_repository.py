from repositories.pgvector_repo import PgVectorRepository
import os

# We mock the DB connection for the repository unit tests
# Real integration test would require spinning up pgvector, which is handled
# in the CI/CD pipeline, but here we just ensure the repo methods are defined correctly.

def test_repo_structure():
    repo = PgVectorRepository()
    assert hasattr(repo, "setup_database")
    assert hasattr(repo, "insert_chunk")
    assert hasattr(repo, "search_chunks")
