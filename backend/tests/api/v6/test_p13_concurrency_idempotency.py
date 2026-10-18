import pytest
import os
import tempfile
import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app.main import app
from app.api.auth import get_current_user, get_current_active_user
from app.models.domain import CaseFile, User, Tenant, UploadedDocument
from app.models.v6.case_workflow import CaseWorkflow
from app.models.v6.supplier import Supplier
from app.models.v6.supplier_selection import SupplierSelectionFinal, SupplierSelectionAttempt
from app.models.v6.supplier_offer import SupplierOffer
from app.models.v6.supplier_profile import SupplierProfile
from app.models.v6.case_requirement_matrix import CaseRequirementMatrix
from app.models.v6.offer_evaluation import OfferEvaluation
from app.models.v6.offer_evidence import OfferEvidence
from app.models.v6.offer_requirement_evidence import OfferRequirementEvidence
from app.models.v6.output_template import OutputTemplate
from app.models.v6.generated_output import GeneratedOutput
from app.services.v6.reporting.technical_report_service import TechnicalReportService
from tests.conftest import TestingSessionLocal

@pytest.fixture
def conc_setup(db_session):
    tenant = db_session.query(Tenant).filter_by(id="mega_tenant").first()
    if not tenant:
        tenant = Tenant(id="mega_tenant", name="Mega Tenant")
        db_session.add(tenant)
        db_session.flush()

    op = db_session.query(User).filter_by(id=20).first()
    if not op:
        op = User(
            id=20,
            username="op_conc",
            role="OPERATOR",
            tenant_id="mega_tenant",
            password_hash="mock",
            tenant_resolution_status="RESOLVED",
            is_active=True
        )
        db_session.add(op)

    sup = db_session.query(User).filter_by(id=21).first()
    if not sup:
        sup = User(
            id=21,
            username="sup_conc",
            role="SUPERVISOR",
            tenant_id="mega_tenant",
            password_hash="mock",
            tenant_resolution_status="RESOLVED",
            is_active=True
        )
        db_session.add(sup)

    sup2 = db_session.query(User).filter_by(id=22).first()
    if not sup2:
        sup2 = User(
            id=22,
            username="sup2_conc",
            role="SUPERVISOR",
            tenant_id="mega_tenant",
            password_hash="mock",
            tenant_resolution_status="RESOLVED",
            is_active=True
        )
        db_session.add(sup2)
    db_session.flush()

    case = CaseFile(
        title="Expediente Concurrencia",
        contract_type="BIENES",
        status="APPROVED",
        tenant_id="mega_tenant",
        assigned_to_user_id=op.id,
        traceability_regime="P12_STRICT"
    )
    db_session.add(case)
    db_session.flush()

    wf = CaseWorkflow(case_id=case.id, status="APPROVED", supervisor_id=sup.id)
    db_session.add(wf)

    supplier = db_session.query(Supplier).filter_by(ruc="20800100209", tenant_id="mega_tenant").first()
    if not supplier:
        supplier = Supplier(tenant_id="mega_tenant", ruc="20800100209", business_name="Concurrencia SAC")
        db_session.add(supplier)
        db_session.flush()

    profile = db_session.query(SupplierProfile).filter_by(supplier_id=supplier.id).first()
    if not profile:
        profile = SupplierProfile(supplier_id=supplier.id, validation_status="VERIFIED")
        db_session.add(profile)
        db_session.flush()

    offer = SupplierOffer(
        case_id=case.id,
        supplier_id=supplier.id,
        status="SELECTED",
        currency="PEN",
        price=18000.0,
        total_amount=18000.0
    )
    db_session.add(offer)
    db_session.flush()

    attempt = SupplierSelectionAttempt(
        case_id=case.id,
        supplier_offer_id=offer.id,
        selected_by=op.id,
        status="UNDER_REVIEW"
    )
    db_session.add(attempt)
    db_session.flush()

    final_sel = SupplierSelectionFinal(case_id=case.id, attempt_id=attempt.id)
    db_session.add(final_sel)

    real_doc_path = os.path.join(tempfile.gettempdir(), f"doc_conc_{case.id}.pdf")
    with open(real_doc_path, "wb") as f:
        f.write(b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>\nendobj\n4 0 obj\n<< /Length 30 >>\nstream\nBT /F1 12 Tf 100 700 Td (Cumple) Tj ET\nendstream\nendobj\nxref\n0 5\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n0000000201 00000 n \ntrailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n282\n%%EOF\n")

    doc = UploadedDocument(
        case_id=case.id,
        document_type="requirement",
        original_filename="doc_conc.pdf",
        stored_path=real_doc_path,
        mime_type="application/pdf"
    )
    db_session.add(doc)
    db_session.flush()

    req = CaseRequirementMatrix(case_id=case.id, requirement_type="TECHNICAL", description="Requisito Conc", mandatory=True)
    db_session.add(req)
    db_session.flush()

    ev = OfferEvaluation(supplier_offer_id=offer.id, requirement_id=req.id, status="PASSED", validated_by=op.id)
    db_session.add(ev)

    offer_ev = OfferEvidence(supplier_offer_id=offer.id, document_id=doc.id, document_type="Ficha Tecnica", fragment="Cumple", page=1)
    db_session.add(offer_ev)
    db_session.flush()

    ore = OfferRequirementEvidence(
        case_id=case.id,
        supplier_offer_id=offer.id,
        requirement_id=req.id,
        offer_evidence_id=offer_ev.id,
        document_id=doc.id,
        page=1,
        fragment="Cumple",
        verified_by=op.id,
        verification_status="VERIFIED"
    )
    db_session.add(ore)

    t1 = db_session.query(OutputTemplate).filter_by(type="INFORME_TECNICO_EVALUACION", version="1.0").first()
    if not t1:
        t1_content = "<div>v1.0 {{ selected_supplier_name }}</div>"
        t1 = OutputTemplate(
            type="INFORME_TECNICO_EVALUACION",
            version="1.0",
            entity_name="Abast-gp",
            content=t1_content,
            checksum=hashlib.sha256(t1_content.encode("utf-8")).hexdigest(),
            status="ACTIVE"
        )
        db_session.add(t1)

    t2 = db_session.query(OutputTemplate).filter_by(type="INFORME_TECNICO_EVALUACION", version="2.0").first()
    if not t2:
        t2_content = "<div>v2.0 {{ selected_supplier_name }}</div>"
        t2 = OutputTemplate(
            type="INFORME_TECNICO_EVALUACION",
            version="2.0",
            entity_name="Abast-gp",
            content=t2_content,
            checksum=hashlib.sha256(t2_content.encode("utf-8")).hexdigest(),
            status="ACTIVE"
        )
        db_session.add(t2)

    db_session.commit()

    return {"case": case, "op": op, "sup": sup, "sup2": sup2, "t1": t1, "t2": t2}

def set_user(user: User):
    def override():
        return user
    app.dependency_overrides[get_current_user] = override
    app.dependency_overrides[get_current_active_user] = override

def test_idempotent_retry_same_payload(client: TestClient, conc_setup):
    case = conc_setup["case"]
    op = conc_setup["op"]
    set_user(op)

    # First request
    res1 = client.post(
        f"/api/v6/cases/{case.id}/reports/p13/generate",
        json={"template_version": "1.0", "idempotency_key": "IDEMP-KEY-999"}
    )
    assert res1.status_code == 200
    data1 = res1.json()

    # Replay identical request
    res2 = client.post(
        f"/api/v6/cases/{case.id}/reports/p13/generate",
        json={"template_version": "1.0", "idempotency_key": "IDEMP-KEY-999"}
    )
    assert res2.status_code == 200
    data2 = res2.json()

    assert data1["id"] == data2["id"]
    assert data1["version_number"] == data2["version_number"]
    assert data1["snapshot_hash"] == data2["snapshot_hash"]

def test_idempotency_key_collision_different_payload(client: TestClient, conc_setup):
    case = conc_setup["case"]
    op = conc_setup["op"]
    set_user(op)

    # First request with template 1.0
    res1 = client.post(
        f"/api/v6/cases/{case.id}/reports/p13/generate",
        json={"template_version": "1.0", "idempotency_key": "COLLISION-KEY-001"}
    )
    assert res1.status_code == 200

    # Second request with SAME key but DIFFERENT template 2.0
    res2 = client.post(
        f"/api/v6/cases/{case.id}/reports/p13/generate",
        json={"template_version": "2.0", "idempotency_key": "COLLISION-KEY-001"}
    )
    assert res2.status_code == 409
    assert "Conflicto de idempotencia" in res2.json()["detail"]

def test_version_number_unique_constraint_enforced_in_postgresql(db_session, conc_setup):
    case = conc_setup["case"]
    t1 = conc_setup["t1"]
    op = conc_setup["op"]

    out1 = GeneratedOutput(
        case_id=case.id,
        template_id=t1.id,
        template_version=t1.version,
        content_rendered="html 1",
        generation_hash="h1",
        generated_by=op.id,
        accuracy_gate_result="PASS",
        source_snapshot={},
        status="GENERATED",
        version_number=1,
        report_kind="INFORME_TECNICO_EVALUACION"
    )
    db_session.add(out1)
    db_session.commit()

    # Try inserting duplicate version for P13
    out2 = GeneratedOutput(
        case_id=case.id,
        template_id=t1.id,
        template_version=t1.version,
        content_rendered="html 2",
        generation_hash="h2",
        generated_by=op.id,
        accuracy_gate_result="PASS",
        source_snapshot={},
        status="GENERATED",
        version_number=1,  # Duplicate!
        report_kind="INFORME_TECNICO_EVALUACION"
    )
    db_session.add(out2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

def test_partial_unique_index_allows_duplicate_legacy_condiciones(db_session, conc_setup):
    case = conc_setup["case"]
    t1 = conc_setup["t1"]
    op = conc_setup["op"]

    # Two legacy outputs with report_kind='CONDICIONES' and version_number=1
    leg1 = GeneratedOutput(
        case_id=case.id,
        template_id=t1.id,
        template_version=t1.version,
        content_rendered="legacy 1",
        generation_hash="hleg1",
        generated_by=op.id,
        accuracy_gate_result="PASS",
        source_snapshot={},
        status="GENERATED",
        version_number=1,
        report_kind="CONDICIONES"
    )
    leg2 = GeneratedOutput(
        case_id=case.id,
        template_id=t1.id,
        template_version=t1.version,
        content_rendered="legacy 2",
        generation_hash="hleg2",
        generated_by=op.id,
        accuracy_gate_result="PASS",
        source_snapshot={},
        status="GENERATED",
        version_number=1,  # Same version number for legacy
        report_kind="CONDICIONES"
    )
    db_session.add(leg1)
    db_session.add(leg2)
    # Must succeed without error because partial index only applies to INFORME_TECNICO_EVALUACION
    db_session.commit()
    assert leg1.id != leg2.id

def test_sequential_versioning_increments_after_rejection(client: TestClient, conc_setup):
    case = conc_setup["case"]
    op = conc_setup["op"]
    sup = conc_setup["sup"]

    set_user(op)
    r1 = client.post(f"/api/v6/cases/{case.id}/reports/p13/generate", json={})
    assert r1.status_code == 200
    v1_id = r1.json()["id"]
    assert r1.json()["version_number"] == 1

    client.post(f"/api/v6/cases/{case.id}/reports/p13/{v1_id}/submit-review", json={})

    set_user(sup)
    client.post(f"/api/v6/cases/{case.id}/reports/p13/{v1_id}/reject", json={"rejection_reason": "Rechazado"})

    set_user(op)
    r2 = client.post(f"/api/v6/cases/{case.id}/reports/p13/generate", json={})
    assert r2.status_code == 200
    assert r2.json()["version_number"] == 2

def test_real_concurrency_same_idempotency_key(conc_setup):
    """
    B11: Dos conexiones PostgreSQL independientes y simultáneas solicitando generación
    con la MISMA clave de idempotencia coordinadas por barrera threading.Barrier.
    Garantiza: exactamente 1 registro creado en base de datos, ambas conexiones
    obtienen la misma entidad con mismo id y versión.
    """
    case = conc_setup["case"]
    op = conc_setup["op"]
    barrier = threading.Barrier(2)
    results = []
    errors = []

    def worker():
        session = TestingSessionLocal()
        try:
            barrier.wait(timeout=10)
            res = TechnicalReportService.generate_report(
                db=session,
                case_id=case.id,
                user_id=op.id,
                tenant_id="mega_tenant",
                template_version="1.0",
                idempotency_key="REAL-CONCUR-KEY-001"
            )
            results.append(res.id)
        except Exception as e:
            try:
                session.rollback()
            except Exception:
                pass
            errors.append(e)
        finally:
            try:
                session.rollback()
            except Exception:
                pass
            session.close()
            TestingSessionLocal.remove()

    with ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(worker)
        f2 = executor.submit(worker)
        f1.result()
        f2.result()

    assert len(errors) == 0, f"Errores en concurrencia: {errors}"
    assert len(results) == 2
    assert results[0] == results[1], f"Esperado mismo ID de reporte, obtenido: {results}"

    # Verificar en DB que solo existe un registro para esa clave
    verify_session = TestingSessionLocal()
    try:
        count = verify_session.query(GeneratedOutput).filter_by(
            case_id=case.id,
            idempotency_key="REAL-CONCUR-KEY-001"
        ).count()
    finally:
        try:
            verify_session.rollback()
        except Exception:
            pass
        verify_session.close()
        TestingSessionLocal.remove()
    assert count == 1

def test_real_concurrency_different_keys_strict_versioning(conc_setup):
    """
    B11: Dos conexiones PostgreSQL independientes solicitando generación simultánea
    para el MISMO expediente con CLAVES DISTINTAS coordinadas por barrera.
    El bloqueo por fila de CaseFile debe serializar la asignación de versiones:
    una genera la versión N y la otra la versión N+1 sin colisión de unicidad.
    """
    case = conc_setup["case"]
    op = conc_setup["op"]
    barrier = threading.Barrier(2)
    versions = []
    errors = []

    def worker(key_suffix):
        session = TestingSessionLocal()
        try:
            barrier.wait(timeout=10)
            res = TechnicalReportService.generate_report(
                db=session,
                case_id=case.id,
                user_id=op.id,
                tenant_id="mega_tenant",
                template_version="1.0",
                idempotency_key=f"DIFF-KEY-{key_suffix}"
            )
            versions.append(res.version_number)
        except Exception as e:
            try:
                session.rollback()
            except Exception:
                pass
            errors.append(e)
        finally:
            try:
                session.rollback()
            except Exception:
                pass
            session.close()
            TestingSessionLocal.remove()

    with ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(worker, "ALPHA")
        f2 = executor.submit(worker, "BETA")
        f1.result()
        f2.result()

    assert len(errors) == 0, f"Errores en concurrencia: {errors}"
    assert len(versions) == 2
    assert len(set(versions)) == 2, f"Se esperaban números de versión distintos, obtenido: {versions}"

def test_real_concurrency_simultaneous_approve_and_reject(conc_setup):
    """
    B11: Carrera crítica entre aprobación y rechazo concurrentes sobre un informe en UNDER_REVIEW.
    Dos supervisores distintos ejecutando simultáneamente en conexiones DB independientes.
    Una sola transición terminal debe triunfar; la otra debe ser rechazada con conflicto 409.
    """
    case = conc_setup["case"]
    op = conc_setup["op"]
    sup1 = conc_setup["sup"]
    sup2 = conc_setup["sup2"]

    # Crear informe y enviarlo a UNDER_REVIEW
    setup_session = TestingSessionLocal()
    try:
        rep = TechnicalReportService.generate_report(
            db=setup_session,
            case_id=case.id,
            user_id=op.id,
            tenant_id="mega_tenant",
            template_version="1.0",
            idempotency_key=f"RACE-APPR-REJ-{case.id}"
        )
        rep = TechnicalReportService.submit_for_review(
            db=setup_session,
            report_id=rep.id,
            user_id=op.id,
            tenant_id="mega_tenant"
        )
        rep_id = rep.id
    finally:
        try:
            setup_session.rollback()
        except Exception:
            pass
        setup_session.close()
        TestingSessionLocal.remove()

    barrier = threading.Barrier(2)
    outcomes = []

    def worker_approve():
        session = TestingSessionLocal()
        try:
            barrier.wait(timeout=10)
            res = TechnicalReportService.approve_report(
                db=session,
                report_id=rep_id,
                supervisor_id=sup1.id,
                tenant_id="mega_tenant",
                user_role="SUPERVISOR",
                approval_notes="Aprobado en carrera concurrente"
            )
            outcomes.append(("APPROVE_SUCCESS", res.status))
        except HTTPException as he:
            try:
                session.rollback()
            except Exception:
                pass
            outcomes.append(("APPROVE_FAIL", he.status_code))
        except Exception as e:
            try:
                session.rollback()
            except Exception:
                pass
            outcomes.append(("APPROVE_FAIL", str(e)))
        finally:
            try:
                session.rollback()
            except Exception:
                pass
            session.close()
            TestingSessionLocal.remove()

    def worker_reject():
        session = TestingSessionLocal()
        try:
            barrier.wait(timeout=10)
            res = TechnicalReportService.reject_report(
                db=session,
                report_id=rep_id,
                supervisor_id=sup2.id,
                tenant_id="mega_tenant",
                user_role="SUPERVISOR",
                rejection_reason="Rechazado en carrera concurrente"
            )
            outcomes.append(("REJECT_SUCCESS", res.status))
        except HTTPException as he:
            try:
                session.rollback()
            except Exception:
                pass
            outcomes.append(("REJECT_FAIL", he.status_code))
        except Exception as e:
            try:
                session.rollback()
            except Exception:
                pass
            outcomes.append(("REJECT_FAIL", str(e)))
        finally:
            try:
                session.rollback()
            except Exception:
                pass
            session.close()
            TestingSessionLocal.remove()

    with ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(worker_approve)
        f2 = executor.submit(worker_reject)
        f1.result()
        f2.result()

    successes = [o for o in outcomes if "SUCCESS" in o[0]]
    failures = [o for o in outcomes if "FAIL" in o[0]]

    assert len(successes) == 1, f"Se esperaba exactamente un ganador en la carrera: {outcomes}"
    assert len(failures) == 1, f"Se esperaba exactamente un fallo (409): {outcomes}"
    assert failures[0][1] == 409

    # Verificar que el estado final en DB es terminal y consistente
    chk_session = TestingSessionLocal()
    try:
        final_rep = chk_session.query(GeneratedOutput).filter_by(id=rep_id).first()
        assert final_rep.status in ["APPROVED", "REJECTED"]
    finally:
        try:
            chk_session.rollback()
        except Exception:
            pass
        chk_session.close()
        TestingSessionLocal.remove()

