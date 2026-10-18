from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from typing import List, Optional, Tuple
import json
import os

from app.core.database import get_db
from app.api.auth import get_current_active_user, verify_case_access, require_role
from app.api.exceptions import NotFoundException, ForbiddenException
from app.models.domain import User, CaseFile, AuditLog
from app.models.v6.supplier_selection import SupplierSelectionFinal, SupplierSelectionAttempt
from app.models.v6.supplier_offer import SupplierOffer
from app.models.v6.supplier import Supplier
from app.models.v6.order_preparation_profile import OrderPreparationProfile
from app.models.v6.output_template import OutputTemplate
from app.models.v6.generated_output import GeneratedOutput
from app.services.v6.engines.accuracy_gate import ContractAccuracyGate
from app.services.v6.engines.template_engine import OutputTemplateEngine

from app.schemas.v6.report_schemas import (
    TechnicalReportGenerateRequest,
    TechnicalReportReviewSubmitRequest,
    TechnicalReportApproveRequest,
    TechnicalReportRejectRequest,
    TechnicalReportResponse,
    TechnicalReportListResponse,
    TechnicalReportIntegrityResponse
)
from app.services.v6.reporting.technical_report_service import TechnicalReportService

router = APIRouter()

# ==============================================================================
# ENDPOINTS P13: INFORME TÉCNICO DE EVALUACIÓN Y SELECCIÓN INTERNA
# ==============================================================================

@router.post(
    "/cases/{case_id}/reports/p13/generate",
    response_model=TechnicalReportResponse,
    status_code=200
)
def generate_p13_report(
    case_id: int,
    payload: TechnicalReportGenerateRequest = TechnicalReportGenerateRequest(),
    case: CaseFile = Depends(verify_case_access),
    current_user: User = Depends(require_role(["ADMIN", "OPERATOR", "SUPERVISOR"])),
    db: Session = Depends(get_db)
):
    """
    Genera una nueva versión congelada del Informe Técnico de Evaluación (P13).
    Aplica bloqueo de fila, validación fail-closed de la selección y snapshot inmutable.
    """
    output = TechnicalReportService.generate_report(
        db=db,
        case_id=case.id,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        template_version=payload.template_version or "1.0",
        idempotency_key=payload.idempotency_key
    )
    return output

@router.get(
    "/cases/{case_id}/reports/p13",
    response_model=TechnicalReportListResponse
)
def list_p13_reports(
    case_id: int,
    case: CaseFile = Depends(verify_case_access),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Lista el historial cronológico y de versiones de informes técnicos P13 del caso.
    """
    reports = (
        db.query(GeneratedOutput)
        .filter(
            GeneratedOutput.case_id == case.id,
            GeneratedOutput.report_kind == TechnicalReportService.REPORT_KIND
        )
        .order_by(GeneratedOutput.version_number.desc())
        .all()
    )
    return {
        "reports": reports,
        "total": len(reports),
        "total_reports": len(reports),
        "case_id": case.id
    }

@router.get(
    "/cases/{case_id}/reports/p13/{report_id}",
    response_model=TechnicalReportResponse
)
def get_p13_report_detail(
    case_id: int,
    report_id: int,
    case: CaseFile = Depends(verify_case_access),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Obtiene el detalle completo de un informe técnico P13 por ID.
    """
    report = (
        db.query(GeneratedOutput)
        .filter(
            GeneratedOutput.id == report_id,
            GeneratedOutput.case_id == case.id,
            GeneratedOutput.report_kind == TechnicalReportService.REPORT_KIND
        )
        .first()
    )
    if not report:
        raise NotFoundException("Informe técnico no encontrado.")
    return report

@router.post(
    "/cases/{case_id}/reports/p13/{report_id}/submit-review",
    response_model=TechnicalReportResponse
)
def submit_p13_report_for_review(
    case_id: int,
    report_id: int,
    payload: TechnicalReportReviewSubmitRequest = TechnicalReportReviewSubmitRequest(),
    case: CaseFile = Depends(verify_case_access),
    current_user: User = Depends(require_role(["ADMIN", "OPERATOR", "SUPERVISOR"])),
    db: Session = Depends(get_db)
):
    """
    Remite un informe técnico de GENERATED a UNDER_REVIEW para revisión formal.
    Idempotente si ya se encuentra en UNDER_REVIEW.
    """
    report = (
        db.query(GeneratedOutput)
        .filter(
            GeneratedOutput.id == report_id,
            GeneratedOutput.case_id == case.id,
            GeneratedOutput.report_kind == TechnicalReportService.REPORT_KIND
        )
        .first()
    )
    if not report:
        raise NotFoundException("Informe técnico no encontrado.")

    updated = TechnicalReportService.submit_for_review(
        db=db,
        report_id=report_id,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        notes=payload.notes
    )
    return updated

@router.post(
    "/cases/{case_id}/reports/p13/{report_id}/approve",
    response_model=TechnicalReportResponse
)
def approve_p13_report(
    case_id: int,
    report_id: int,
    payload: TechnicalReportApproveRequest = TechnicalReportApproveRequest(),
    case: CaseFile = Depends(verify_case_access),
    current_user: User = Depends(require_role(["ADMIN", "SUPERVISOR"])),
    db: Session = Depends(get_db)
):
    """
    Aprobación formal del informe P13 por SUPERVISOR o ADMIN independiente.
    Enforces SoD: el autor no puede aprobar su propio informe.
    Congela HTML definitivo y genera PDF con verificación criptográfica.
    """
    report = (
        db.query(GeneratedOutput)
        .filter(
            GeneratedOutput.id == report_id,
            GeneratedOutput.case_id == case.id,
            GeneratedOutput.report_kind == TechnicalReportService.REPORT_KIND
        )
        .first()
    )
    if not report:
        raise NotFoundException("Informe técnico no encontrado.")

    approved = TechnicalReportService.approve_report(
        db=db,
        report_id=report_id,
        supervisor_id=current_user.id,
        tenant_id=current_user.tenant_id,
        user_role=current_user.role,
        approval_notes=payload.approval_notes
    )
    return approved

@router.post(
    "/cases/{case_id}/reports/p13/{report_id}/reject",
    response_model=TechnicalReportResponse
)
def reject_p13_report(
    case_id: int,
    report_id: int,
    payload: TechnicalReportRejectRequest,
    case: CaseFile = Depends(verify_case_access),
    current_user: User = Depends(require_role(["ADMIN", "SUPERVISOR"])),
    db: Session = Depends(get_db)
):
    """
    Rechazo formal motivado de un informe en UNDER_REVIEW.
    El rechazo es terminal para esa versión. La subsanación requiere nueva generación.
    """
    report = (
        db.query(GeneratedOutput)
        .filter(
            GeneratedOutput.id == report_id,
            GeneratedOutput.case_id == case.id,
            GeneratedOutput.report_kind == TechnicalReportService.REPORT_KIND
        )
        .first()
    )
    if not report:
        raise NotFoundException("Informe técnico no encontrado.")

    rejected = TechnicalReportService.reject_report(
        db=db,
        report_id=report_id,
        supervisor_id=current_user.id,
        tenant_id=current_user.tenant_id,
        user_role=current_user.role,
        rejection_reason=payload.rejection_reason
    )
    return rejected

@router.get(
    "/cases/{case_id}/reports/p13/{report_id}/export/html",
    response_class=HTMLResponse
)
def export_p13_report_html(
    case_id: int,
    report_id: int,
    case: CaseFile = Depends(verify_case_access),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Descarga del HTML definitivo aprobado.
    Operación puramente de lectura (NO muta estado a EXPORTED).
    Registra evento de auditoría de descarga.
    """
    report = (
        db.query(GeneratedOutput)
        .filter(
            GeneratedOutput.id == report_id,
            GeneratedOutput.case_id == case.id,
            GeneratedOutput.report_kind == TechnicalReportService.REPORT_KIND
        )
        .first()
    )
    if not report:
        raise NotFoundException("Informe técnico no encontrado.")

    html_content = TechnicalReportService.get_export_html(
        db=db,
        report_id=report_id,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id
    )
    pdf_fname = getattr(report, "pdf_filename", None) or (os.path.basename(report.pdf_storage_path) if report.pdf_storage_path else None)
    safe_filename = pdf_fname.replace(".pdf", ".html") if pdf_fname else f"informe_tecnico_{report_id}.html"
    return HTMLResponse(
        content=html_content,
        status_code=200,
        headers={"Content-Disposition": f'attachment; filename="{safe_filename}"'}
    )

@router.get(
    "/cases/{case_id}/reports/p13/{report_id}/export/pdf"
)
def export_p13_report_pdf(
    case_id: int,
    report_id: int,
    case: CaseFile = Depends(verify_case_access),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Descarga del artefacto PDF binario congelado y verificado.
    Operación puramente de lectura (NO muta estado a EXPORTED).
    Registra evento de auditoría de descarga.
    """
    report = (
        db.query(GeneratedOutput)
        .filter(
            GeneratedOutput.id == report_id,
            GeneratedOutput.case_id == case.id,
            GeneratedOutput.report_kind == TechnicalReportService.REPORT_KIND
        )
        .first()
    )
    if not report:
        raise NotFoundException("Informe técnico no encontrado.")

    pdf_bytes, filename = TechnicalReportService.get_export_pdf_bytes(
        db=db,
        report_id=report_id,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )

@router.get(
    "/cases/{case_id}/reports/p13/{report_id}/verify-integrity",
    response_model=TechnicalReportIntegrityResponse
)
def verify_p13_report_integrity(
    case_id: int,
    report_id: int,
    case: CaseFile = Depends(verify_case_access),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Verifica la integridad criptográfica en los 3 dominios (snapshot, html, pdf).
    """
    report = (
        db.query(GeneratedOutput)
        .filter(
            GeneratedOutput.id == report_id,
            GeneratedOutput.case_id == case.id,
            GeneratedOutput.report_kind == TechnicalReportService.REPORT_KIND
        )
        .first()
    )
    if not report:
        raise NotFoundException("Informe técnico no encontrado.")

    result = TechnicalReportService.verify_integrity(
        db=db,
        report_id=report_id,
        tenant_id=current_user.tenant_id
    )
    return result

@router.get(
    "/cases/{case_id}/reports/p13/{report_id}/integrity",
    response_model=TechnicalReportIntegrityResponse
)
def verify_p13_report_integrity_short(
    case_id: int,
    report_id: int,
    case: CaseFile = Depends(verify_case_access),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    return verify_p13_report_integrity(case_id, report_id, case, current_user, db)

# Direct alias routes by report_id with full tenant and case isolation
def _get_verified_report(report_id: int, user: User, db: Session) -> Tuple[GeneratedOutput, CaseFile]:
    report = (
        db.query(GeneratedOutput)
        .filter(
            GeneratedOutput.id == report_id,
            GeneratedOutput.report_kind == TechnicalReportService.REPORT_KIND
        )
        .first()
    )
    if not report:
        raise NotFoundException("Informe técnico no encontrado.")
    case = (
        db.query(CaseFile)
        .filter(
            CaseFile.id == report.case_id,
            CaseFile.tenant_id == user.tenant_id
        )
        .first()
    )
    if not case:
        raise NotFoundException("Informe técnico no encontrado.")
    if user.role not in ["ADMIN", "SUPERVISOR"] and case.assigned_to_user_id != user.id:
        raise NotFoundException("Informe técnico no encontrado.")
    return report, case

@router.post("/reports/p13/cases/{case_id}/generate", response_model=TechnicalReportResponse, status_code=200)
def generate_p13_report_direct(
    case_id: int,
    payload: TechnicalReportGenerateRequest = TechnicalReportGenerateRequest(),
    case: CaseFile = Depends(verify_case_access),
    current_user: User = Depends(require_role(["ADMIN", "OPERATOR", "SUPERVISOR"])),
    db: Session = Depends(get_db)
):
    return generate_p13_report(case_id, payload, case, current_user, db)

@router.get("/reports/p13/cases/{case_id}/reports", response_model=TechnicalReportListResponse)
def list_p13_reports_direct(
    case_id: int,
    case: CaseFile = Depends(verify_case_access),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    return list_p13_reports(case_id, case, current_user, db)

@router.get("/reports/p13/reports/{report_id}", response_model=TechnicalReportResponse)
def get_p13_report_direct(
    report_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    report, _ = _get_verified_report(report_id, current_user, db)
    return report

@router.post("/reports/p13/reports/{report_id}/submit-review", response_model=TechnicalReportResponse)
def submit_p13_report_review_direct(
    report_id: int,
    payload: TechnicalReportReviewSubmitRequest = TechnicalReportReviewSubmitRequest(),
    current_user: User = Depends(require_role(["ADMIN", "OPERATOR", "SUPERVISOR"])),
    db: Session = Depends(get_db)
):
    report, case = _get_verified_report(report_id, current_user, db)
    return submit_p13_report_for_review(report.case_id, report_id, payload, case, current_user, db)

@router.post("/reports/p13/reports/{report_id}/approve", response_model=TechnicalReportResponse)
def approve_p13_report_direct(
    report_id: int,
    payload: TechnicalReportApproveRequest = TechnicalReportApproveRequest(),
    current_user: User = Depends(require_role(["ADMIN", "SUPERVISOR"])),
    db: Session = Depends(get_db)
):
    report, case = _get_verified_report(report_id, current_user, db)
    return approve_p13_report(report.case_id, report_id, payload, case, current_user, db)

@router.post("/reports/p13/reports/{report_id}/reject", response_model=TechnicalReportResponse)
def reject_p13_report_direct(
    report_id: int,
    payload: TechnicalReportRejectRequest = ...,
    current_user: User = Depends(require_role(["ADMIN", "SUPERVISOR"])),
    db: Session = Depends(get_db)
):
    report, case = _get_verified_report(report_id, current_user, db)
    return reject_p13_report(report.case_id, report_id, payload, case, current_user, db)

@router.get("/reports/p13/reports/{report_id}/export/html", response_class=HTMLResponse)
def export_p13_report_html_direct(
    report_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    report, case = _get_verified_report(report_id, current_user, db)
    return export_p13_report_html(report.case_id, report_id, case, current_user, db)

@router.get("/reports/p13/reports/{report_id}/export/pdf")
def export_p13_report_pdf_direct(
    report_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    report, case = _get_verified_report(report_id, current_user, db)
    return export_p13_report_pdf(report.case_id, report_id, case, current_user, db)

@router.get("/reports/p13/reports/{report_id}/integrity", response_model=TechnicalReportIntegrityResponse)
def verify_p13_report_integrity_direct(
    report_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    report, case = _get_verified_report(report_id, current_user, db)
    return verify_p13_report_integrity(report.case_id, report_id, case, current_user, db)



# ==============================================================================
# ENDPOINTS HISTÓRICOS Y DE COMPATIBILIDAD (RECTIFICADOS)
# ==============================================================================

@router.post("/cases/{case_id}/prepare-output")
def prepare_output(
    case_id: int,
    case: CaseFile = Depends(verify_case_access),
    current_user: User = Depends(require_role(["ADMIN", "OPERATOR", "SUPERVISOR"])),
    db: Session = Depends(get_db)
):
    """
    Ruta histórica de generación de CONDICIONES contractuales.
    Rectificada: se eliminan los mocks ("Tech Corp", RUC inventado, 5000).
    Exige selección y perfil auténticos.
    """
    # 1. Gate Check
    gate_result = ContractAccuracyGate.validate_for_generation(db, case_id)
    if gate_result == "ACCURACY_FAILED":
        raise HTTPException(status_code=400, detail="El expediente no supero el Contract Accuracy Gate.")
        
    # 2. Get Selection & Profile real
    selection = db.query(SupplierSelectionFinal).filter_by(case_id=case_id).first()
    if not selection:
        raise HTTPException(status_code=400, detail="No existe seleccion final aprobada.")
        
    profile = db.query(OrderPreparationProfile).filter_by(supplier_selection_final_id=selection.id).first()
    if not profile:
        attempt = None
        if hasattr(selection, "attempt") and selection.attempt:
            attempt = selection.attempt
        elif hasattr(selection, "attempt_id") and selection.attempt_id:
            attempt = db.query(SupplierSelectionAttempt).filter_by(id=selection.attempt_id).first()

        if not attempt or not attempt.supplier_offer_id:
            raise HTTPException(status_code=400, detail="Intento de selección o datos de oferta no disponibles.")

        offer = db.query(SupplierOffer).filter_by(id=attempt.supplier_offer_id).first()
        if not offer or not offer.supplier_id:
            raise HTTPException(status_code=400, detail="Oferta seleccionada o proveedor no encontrado en el caso.")

        sup = db.query(Supplier).filter_by(id=offer.supplier_id).first()
        if not sup or not sup.business_name or not sup.ruc or sup.business_name.strip() == "" or sup.ruc.strip() == "" or sup.ruc.strip() == "NO_RUC":
            raise HTTPException(
                status_code=400,
                detail="Datos del proveedor incompletos (razón social o RUC ausente/inválido). Se rechaza generación con datos sintéticos."
            )
        supplier_name = sup.business_name.strip()
        supplier_ruc = sup.ruc.strip()

        raw_price = offer.total_amount if offer.total_amount is not None else offer.price
        if raw_price is None or float(raw_price) <= 0:
            raise HTTPException(
                status_code=400,
                detail="Importe de la oferta ausente o no positivo. Se rechaza generación con datos sintéticos."
            )
        contract_amount = float(raw_price)

        profile = OrderPreparationProfile(
            supplier_selection_final_id=selection.id,
            supplier_data={"supplier_name": supplier_name, "supplier_ruc": supplier_ruc},
            contracting_data={"contract_amount": contract_amount},
            improvements_data={}
        )
        db.add(profile)
        db.flush()
        
    # 3. Get Templates
    template = db.query(OutputTemplate).filter_by(type="CONDICIONES", status="ACTIVE").first()
    if not template:
        raise HTTPException(status_code=404, detail="Plantilla activa de tipo CONDICIONES no encontrada en catálogo.")
        
    # 4. Engine Render
    snapshot = {**profile.supplier_data, **profile.contracting_data, **(profile.improvements_data or {})}
    try:
        rendered_content, content_hash = OutputTemplateEngine.render_template(template.content, snapshot)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
        
    # 5. Save GeneratedOutput
    output = GeneratedOutput(
        case_id=case_id,
        template_id=template.id,
        content_rendered=rendered_content,
        generation_hash=content_hash,
        generated_by=current_user.id,
        template_version=template.version,
        accuracy_gate_result=gate_result,
        source_snapshot=snapshot,
        status="GENERATED",
        report_kind="CONDICIONES"
    )
    db.add(output)
    
    audit = AuditLog(
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        action="PREPARE_OUTPUT",
        entity_type="CaseFile",
        entity_id=str(case_id),
        details=json.dumps({"hash": content_hash}),
        status="SUCCESS"
    )
    db.add(audit)
    db.commit()
    
    return {"id": output.id, "status": output.status, "hash": output.generation_hash}

@router.get("/cases/{case_id}/outputs")
def list_outputs(
    case_id: int,
    case: CaseFile = Depends(verify_case_access),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    outputs = db.query(GeneratedOutput).filter_by(case_id=case.id).all()
    return [{
        "id": o.id,
        "type": o.report_kind or (o.template.type if o.template else "CONDICIONES"),
        "status": o.status,
        "version_number": o.version_number
    } for o in outputs]

@router.post("/outputs/{output_id}/approve")
def approve_output(
    output_id: int,
    current_user: User = Depends(require_role(["ADMIN", "SUPERVISOR"])),
    db: Session = Depends(get_db)
):
    """
    Ruta histórica de aprobación.
    Rectificada: Si el output es de tipo P13, redirige a las reglas estrictas de P13
    (no permite aprobación directa desde GENERATED ni violación de SoD).
    """
    output = db.query(GeneratedOutput).filter_by(id=output_id).first()
    if not output:
        raise NotFoundException("Output not found")

    case = db.query(CaseFile).filter(
        CaseFile.id == output.case_id,
        CaseFile.tenant_id == current_user.tenant_id
    ).first()
    if not case:
        raise NotFoundException("Output not found")

    # Si es P13, delegar al servicio P13 con todos los controles
    if output.report_kind == TechnicalReportService.REPORT_KIND:
        approved = TechnicalReportService.approve_report(
            db=db,
            report_id=output_id,
            supervisor_id=current_user.id,
            tenant_id=current_user.tenant_id,
            user_role=current_user.role,
            approval_notes="Aprobado mediante ruta heredada"
        )
        return {"id": approved.id, "status": approved.status}

    output.status = "APPROVED"
    output.approved_by = current_user.id
    
    audit = AuditLog(
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        action="APPROVE_OUTPUT",
        entity_type="GeneratedOutput",
        entity_id=str(output.id),
        details=json.dumps({}),
        status="SUCCESS"
    )
    db.add(audit)
    db.commit()
    return {"id": output.id, "status": output.status}

@router.post("/outputs/{output_id}/export")
def export_output(
    output_id: int,
    download: bool = False,
    current_user: User = Depends(require_role(["ADMIN", "OPERATOR", "SUPERVISOR"])),
    db: Session = Depends(get_db)
):
    """
    Ruta histórica de exportación.
    Rectificada [R2-02, R2-10]:
    - Para informes P13: Entrega artefacto PDF binario auténtico sin mutar estado a EXPORTED (mantiene APPROVED).
    - Para outputs legados: Entrega el artefacto generado; si no existe contenido, rechaza con HTTP 400.
      Nunca retorna éxito si solo se registró una constancia.
    """
    output = db.query(GeneratedOutput).filter_by(id=output_id).first()
    if not output:
        raise NotFoundException("Output not found")

    case_query = db.query(CaseFile).filter(
        CaseFile.id == output.case_id,
        CaseFile.tenant_id == current_user.tenant_id
    )
    if current_user.role not in ["ADMIN", "SUPERVISOR"]:
        case_query = case_query.filter(CaseFile.assigned_to_user_id == current_user.id)
    case = case_query.first()
    if not case:
        raise NotFoundException("Output not found")

    if output.status != "APPROVED":
        raise HTTPException(status_code=400, detail="Output must be APPROVED before export")

    if output.report_kind == TechnicalReportService.REPORT_KIND:
        # P13: Entrega artefacto PDF binario real sin cambiar estado a EXPORTED
        pdf_bytes, filename = TechnicalReportService.get_export_pdf_bytes(
            db=db,
            report_id=output.id,
            user_id=current_user.id,
            tenant_id=current_user.tenant_id
        )
        audit = AuditLog(
            user_id=current_user.id,
            tenant_id=current_user.tenant_id,
            action="EXPORT_OUTPUT",
            entity_type="GeneratedOutput",
            entity_id=str(output.id),
            details=json.dumps({
                "report_kind": output.report_kind,
                "status": output.status,
                "filename": filename,
                "delivered_bytes": len(pdf_bytes)
            }),
            status="SUCCESS"
        )
        db.add(audit)
        db.commit()
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )

    # Para outputs legados no-P13 (CONDICIONES):
    if not output.content_rendered or not output.content_rendered.strip():
        raise HTTPException(status_code=400, detail="El output no contiene artefacto generado válido para exportar.")

    output.status = "EXPORTED"
    audit = AuditLog(
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        action="EXPORT_OUTPUT",
        entity_type="GeneratedOutput",
        entity_id=str(output.id),
        details=json.dumps({"content_length": len(output.content_rendered)}),
        status="SUCCESS"
    )
    db.add(audit)
    db.commit()

    if download:
        return Response(
            content=output.content_rendered.encode("utf-8"),
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="output_{output.id}.txt"'}
        )

    return {
        "id": output.id,
        "status": output.status,
        "filename": f"output_{output.id}.txt",
        "content": output.content_rendered,
        "artifact_delivered": True,
        "message": "Artefacto exportado exitosamente."
    }
