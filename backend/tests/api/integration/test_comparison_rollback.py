import pytest
from sqlalchemy import text
from fastapi.testclient import TestClient
from app.main import app
from app.api.auth import get_current_active_user, get_current_user
from app.models.domain import User, CaseFile, FinalConditionComparison, QuotationExtraction, ParsedSection, UploadedDocument
from tests.conftest import TestingSessionLocal

def mock_run_comparison(*args, **kwargs):
    # Devolver dos resultados. El trigger de la DB fallará en el segundo.
    return [
        {"field_name": "Field 1", "status": "Coincide"},
        {"field_name": "Field 2", "status": "No Coincide"}
    ]

@pytest.fixture
def setup_rollback_trigger():
    with TestingSessionLocal() as db:
        # Create a trigger that fails on the second insert for case 998
        db.execute(text("""
            CREATE OR REPLACE FUNCTION fail_second_insert_trg()
            RETURNS trigger AS $$
            DECLARE
                c INTEGER;
            BEGIN
                IF NEW.case_id = 998 THEN
                    SELECT COUNT(*) INTO c FROM final_condition_comparisons WHERE case_id = 998;
                    IF c >= 1 THEN
                        RAISE EXCEPTION 'Simulated PostgreSQL failure on second insert for rollback gate';
                    END IF;
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
        """))
        db.execute(text("""
            CREATE TRIGGER fail_second_insert
            BEFORE INSERT ON final_condition_comparisons
            FOR EACH ROW EXECUTE FUNCTION fail_second_insert_trg();
        """))
        db.commit()

    yield

    # Teardown
    with TestingSessionLocal() as db:
        db.execute(text("DROP TRIGGER IF EXISTS fail_second_insert ON final_condition_comparisons;"))
        db.execute(text("DROP FUNCTION IF EXISTS fail_second_insert_trg();"))
        db.commit()


def test_comparison_rollback_real(setup_mega_tenant, setup_rollback_trigger):
    with TestingSessionLocal() as db:
        case = CaseFile(id=998, tenant_id="mega_tenant", title="Test Title", contract_type="Bienes", status="COMPARING")
        doc = UploadedDocument(id=998, case_id=998, document_type="requirement", original_filename="test.pdf", stored_path="/tmp", mime_type="application/pdf")
        db.add(case)
        db.add(doc)
        db.flush()
        db.add(QuotationExtraction(case_id=998, raw_json={"q": 1}))
        db.add(ParsedSection(case_id=998, document_id=998, is_selected=True, current_text="Forma de pago 30 dias"))
        db.commit()

    from app.api.routers import cases
    original_run_comparison = cases.run_comparison
    cases.run_comparison = mock_run_comparison

    admin_user = User(
        id=1, username="admin", role="ADMIN", is_active=True, must_change_password=False, tenant_id="mega_tenant"
    )
    app.dependency_overrides[get_current_active_user] = lambda: admin_user
    app.dependency_overrides[get_current_user] = lambda: admin_user

    try:
        with TestClient(app) as client:
            response = client.post("/cases/998/comparison/run")

            # El endpoint captura la excepcion general y retorna 500
            assert response.status_code == 500
            assert "error occurred" in response.json()["detail"].lower()
    finally:
        cases.run_comparison = original_run_comparison
        app.dependency_overrides.pop(get_current_active_user, None)
        app.dependency_overrides.pop(get_current_user, None)


    # Verificación en PostgreSQL mediante una sesión nueva (Rollback real)
    with TestingSessionLocal() as db:
        count = db.query(FinalConditionComparison).filter_by(case_id=998).count()
        assert count == 0, "Deberían haber cero filas parciales persistidas"

        case_state = db.query(CaseFile).filter_by(id=998).first()
        assert case_state.status == "COMPARING", "El estado debió retornar a COMPARING al hacer rollback"
