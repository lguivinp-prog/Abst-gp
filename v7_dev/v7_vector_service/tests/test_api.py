from fastapi.testclient import TestClient
from main import app

def test_api_index():
    with TestClient(app) as client:
        response = client.post(
            "/v7/vector/index",
            headers={"x-tenant-id": "tenant-A"},
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
        assert response.status_code == 200
        assert response.json()["status"] == "SUCCESS"

def test_api_search():
    with TestClient(app) as client:
        response = client.post(
            "/v7/vector/search",
            headers={"x-tenant-id": "tenant-A"},
            json={
                "tenant_id": "tenant-A",
                "embedding": [0.1, 0.2, 0.3],
                "top_k": 5
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) >= 1
        assert data["results"][0]["chunk_id"] == "chunk-1"
