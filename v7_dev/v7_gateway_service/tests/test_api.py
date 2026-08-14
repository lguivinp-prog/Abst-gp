from fastapi.testclient import TestClient
from main import app
import jwt
from datetime import datetime, timezone, timedelta
from security.auth import SECRET_KEY

client = TestClient(app)

def create_valid_token():
    payload = {
        "sub": "test_user",
        "tenant_id": "tenant-A",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=15)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")

def test_sanitize_allow():
    token = create_valid_token()
    response = client.post(
        "/v7/gateway/sanitize",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "request_id": "req-123",
            "tenant_context": "tenant-A",
            "policy_version": "1.0",
            "content": "El proveedor tiene RUC 20987654321."
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["decision"] == "ALLOW"
    assert "[RUC_MASKED]" in data["masked_content"]

def test_metrics_endpoint():
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "v7_gateway_latency_ms" in response.text
