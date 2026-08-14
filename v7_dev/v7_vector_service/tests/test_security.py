from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_missing_tenant_header():
    response = client.post(
        "/v7/vector/index",
        json={
            "tenant_id": "tenant-A",
            "chunk_id": "chunk-1",
            "content": "test",
            "embedding": [0.1, 0.2, 0.3],
            "document_hash": "hash123",
            "embedding_model": "test_model",
            "embedding_version": "1.0",
            "source_type": "pdf"
        }
    )
    assert response.status_code == 422 # FastAPI validation error for missing header

def test_tenant_mismatch():
    response = client.post(
        "/v7/vector/index",
        headers={"x-tenant-id": "tenant-B"}, # Header claims B
        json={
            "tenant_id": "tenant-A", # Payload claims A
            "chunk_id": "chunk-1",
            "content": "test",
            "embedding": [0.1, 0.2, 0.3],
            "document_hash": "hash123",
            "embedding_model": "test_model",
            "embedding_version": "1.0",
            "source_type": "pdf"
        }
    )
    # The application logic raises an Exception for mismatch which becomes a 403 error
    assert response.status_code == 403
