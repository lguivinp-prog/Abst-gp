import pytest
import httpx
import threading
import asyncio
from sqlalchemy import text
from app.main import app
from app.api.auth import get_current_active_user
from app.models.domain import User, CaseFile, FinalConditionComparison, QuotationExtraction, ParsedSection, UploadedDocument
from tests.conftest import TestingSessionLocal
import time

first_request_inside_engine = threading.Event()
allow_first_request_to_finish = threading.Event()

def mock_run_comparison(*args, **kwargs):
    first_request_inside_engine.set()
    allow_first_request_to_finish.wait(timeout=10.0)
    return [{"field_name": "Test Field", "status": "Coincide"}]

@pytest.mark.asyncio
async def test_comparison_concurrency_real(setup_mega_tenant, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "FEATURE_ASYNC_PROCESSING", False)
    monkeypatch.setattr(settings, "FEATURE_ASYNC_COMPARISON", False)
    first_request_inside_engine.clear()
    allow_first_request_to_finish.clear()
    
    with TestingSessionLocal() as db:
        case = CaseFile(id=999, tenant_id="mega_tenant", title="Test Title", contract_type="Bienes", status="COMPARING")
        doc = UploadedDocument(id=999, case_id=999, document_type="requirement", original_filename="test.pdf", stored_path="/tmp", mime_type="application/pdf")
        db.add(case)
        db.add(doc)
        db.flush()
        db.add(QuotationExtraction(case_id=999, raw_json={"q": 1}))
        db.add(ParsedSection(case_id=999, document_id=999, is_selected=True, current_text="Forma de pago 30 dias"))
        db.commit()

    from app.api.routers import cases
    original_run_comparison = cases.run_comparison
    cases.run_comparison = mock_run_comparison

    app.dependency_overrides[get_current_active_user] = lambda: User(
        id=1, username="admin", role="ADMIN", is_active=True, must_change_password=False, tenant_id="mega_tenant"
    )

    with TestingSessionLocal() as db:
        db.execute(text("SET statement_timeout = '10s'"))
        db.commit()

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        task1 = asyncio.create_task(client.post("/cases/999/comparison/run"))
        
        while not first_request_inside_engine.is_set():
            await asyncio.sleep(0.1)

        print("\n[CONCURRENCY] First request acquired FOR UPDATE lock.")
        
        task2 = asyncio.create_task(client.post("/cases/999/comparison/run"))
        
        await asyncio.sleep(1.0)
        
        with TestingSessionLocal() as db:
            activity = db.execute(text("""
                SELECT pid, wait_event_type, state, query 
                FROM pg_stat_activity 
                WHERE query LIKE '%FOR UPDATE%' AND pid <> pg_backend_pid()
            """)).fetchall()
            print(f"[CONCURRENCY] PostgreSQL pg_stat_activity: {activity}")
        
        print("[CONCURRENCY] Releasing first request...")
        allow_first_request_to_finish.set()
        
        resp1, resp2 = await asyncio.gather(task1, task2)
        
    cases.run_comparison = original_run_comparison
    app.dependency_overrides.clear()
    
    assert resp1.status_code == 200
    assert resp2.status_code == 200
    
    assert resp1.json()["already_completed"] is False
    assert resp2.json()["already_completed"] is True
    
    with TestingSessionLocal() as db:
        count = db.query(FinalConditionComparison).filter_by(case_id=999).count()
        assert count == 1
        updated_case = db.query(CaseFile).filter_by(id=999).first()
        assert updated_case.status == "READY_GENERATE"
