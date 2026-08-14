from fastapi.testclient import TestClient
from main import app
import jwt
from datetime import datetime, timezone, timedelta
from security.auth import SECRET_KEY

client = TestClient(app)

def test_invalid_jwt():
    response = client.post(
        "/v7/gateway/sanitize",
        headers={"Authorization": "Bearer invalid_token"},
        json={
            "request_id": "req-123",
            "tenant_context": "tenant-A",
            "policy_version": "1.0",
            "content": "test"
        }
    )
    assert response.status_code == 401

def test_expired_jwt():
    payload = {
        "sub": "test_user",
        "tenant_id": "tenant-A",
        "exp": datetime.now(timezone.utc) - timedelta(minutes=15) # Expired
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
    
    response = client.post(
        "/v7/gateway/sanitize",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "request_id": "req-123",
            "tenant_context": "tenant-A",
            "policy_version": "1.0",
            "content": "test"
        }
    )
    assert response.status_code == 401
