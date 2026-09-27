import pytest
import httpx
import os
import time
import tempfile
import fitz  # PyMuPDF
from app.api.auth import get_password_hash
from app.models.domain import User, Tenant
from tests.conftest import TestingSessionLocal

# Assuming backend-app runs at this hostname/port inside the compose network
BASE_URL = os.getenv("API_BASE_URL", "http://backend-app:8000")

@pytest.fixture(scope="module", autouse=True)
def setup_e2e_admin_user():
    with TestingSessionLocal() as db:
        tenant = db.query(Tenant).filter(Tenant.id == "mega_tenant").first()
        if not tenant:
            tenant = Tenant(id="mega_tenant", name="Mega Tenant")
            db.add(tenant)
            db.commit()
        
        hashed = get_password_hash("adminpassword")
        admin = db.query(User).filter(User.username == "admin").first()
        if admin:
            admin.password_hash = hashed
            admin.tenant_id = "mega_tenant"
            admin.tenant_resolution_status = "RESOLVED"
            admin.is_active = True
            admin.must_change_password = False
        else:
            admin = User(
                username="admin",
                password_hash=hashed,
                role="ADMIN",
                is_active=True,
                tenant_id="mega_tenant",
                tenant_resolution_status="RESOLVED",
                must_change_password=False
            )
            db.add(admin)
        db.commit()
    yield

def test_full_document_pipeline():
    with httpx.Client(base_url=BASE_URL, timeout=60.0) as client:
        # Wait for the service to be ready
        for i in range(30):
            try:
                # Basic health check
                client.get("/docs")
                break
            except httpx.ConnectError:
                time.sleep(1)
        else:
            pytest.skip("Backend app did not start in time. Skipping E2E test.")

        # 1. Login
        response = client.post("/auth/token", data={
            "username": "admin",
            "password": "adminpassword"
        })
        assert response.status_code == 200, f"Could not login: {response.text}"
            
        token = response.json().get("access_token")
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Create case
        response = client.post("/cases/", json={
            "title": "E2E Case",
            "contract_type": "bienes"
        }, headers=headers)
        assert response.status_code == 200, f"Case creation failed: {response.text}"
        case_id = response.json()["id"]

        # 3. Upload requirement PDF with valid structural sections
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
            tf_path = tf.name

        doc = fitz.open()
        page = doc.new_page()
        req_text = """I. FINALIDAD PÚBLICA
La contratación tiene por finalidad pública garantizar el servicio de abastecimiento de bienes de oficina.

II. OBJETIVO DE LA CONTRATACIÓN
Adquisición de insumos de cómputo y oficina.

III. CARACTERÍSTICAS Y CONDICIONES DE LA CONTRATACIÓN
1. Plazo de entrega: 15 días calendario.
2. Garantía comercial: 12 meses.
3. Lugar de entrega: Almacén Central.
"""
        page.insert_text(fitz.Point(72, 120), req_text)
        doc.save(tf_path)
        doc.close()

        try:
            with open(tf_path, "rb") as f:
                response = client.post(
                    f"/cases/{case_id}/requirement/upload",
                    files={"file": ("req.pdf", f, "application/pdf")},
                    headers=headers
                )
            assert response.status_code == 200, f"Upload req failed: {response.text}"
            job_id = response.json().get("job_id")
            assert job_id is not None

            # 4. Polling job status
            status_response = None
            for _ in range(30):
                status_response = client.get(f"/cases/jobs/{job_id}", headers=headers)
                if status_response.status_code == 200 and status_response.json().get("status") in ["finished", "failed"]:
                    break
                time.sleep(1)
            
            assert status_response is not None and status_response.json().get("status") == "finished", f"OCR worker failed or timeout: {status_response.text if status_response else 'no response'}"

            # 5. Fetch and confirm sections
            response = client.get(f"/cases/{case_id}/sections", headers=headers)
            assert response.status_code == 200
            sections = response.json()
            assert len(sections) > 0, "No sections parsed"

            # 5.1 Simulate frontend manual review of sections
            for sec in sections:
                if sec.get("review_status") == "pending_review":
                    update_resp = client.put(
                        f"/cases/sections/{sec['id']}",
                        json={
                            "is_selected": True,
                            "review_status": "validated",
                            "current_text": sec.get("current_text", "")
                        },
                        headers=headers
                    )
                    assert update_resp.status_code == 200, f"Failed to validate section {sec['id']}"

            response = client.post(f"/cases/{case_id}/sections/confirm", headers=headers)
            print(f"\nCONFIRM_RESPONSE: {response.status_code} {response.text}")
            assert response.status_code == 200

            # 6. Upload quotation PDF
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf_quot:
                tf_quot_path = tf_quot.name

            doc_q = fitz.open()
            page_q = doc_q.new_page()
            quot_text = """COTIZACIÓN COMERCIAL
PROVEEDOR: DISTRIBUIDORA PERUANA SAC
RUC: 20456789012

1. Plazo de entrega: 15 días calendario.
2. Garantía: 12 meses.
3. Lugar de entrega: Almacén Central.
4. Monto total: S/ 25,000.00
"""
            page_q.insert_text(fitz.Point(72, 120), quot_text)
            doc_q.save(tf_quot_path)
            doc_q.close()

            try:
                with open(tf_quot_path, "rb") as f:
                    response = client.post(
                        f"/cases/{case_id}/quotation/upload",
                        files={"file": ("quot.pdf", f, "application/pdf")},
                        headers=headers
                    )
                assert response.status_code == 200

                # 7. Run Comparison
                response = client.post(f"/cases/{case_id}/comparison/run", headers=headers)
                assert response.status_code == 200
                
                # 8. Check Results
                response = client.get(f"/cases/{case_id}/comparison", headers=headers)
                assert response.status_code == 200
                results = response.json()
                assert isinstance(results, list)
                
                # 9. Generate HTML
                response = client.post(f"/cases/{case_id}/generate/html", headers=headers)
                assert response.status_code == 200
            finally:
                if os.path.exists(tf_quot_path):
                    os.remove(tf_quot_path)
        finally:
            if os.path.exists(tf_path):
                os.remove(tf_path)
