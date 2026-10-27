from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List
import os
import tempfile
import uuid
import json
from pathlib import Path

import rq

from app.core.config import settings
from app.core.database import get_db
from app.core.redis import task_queue
from app.storage.factory import get_storage

from app.models.domain import (
    CaseFile,
    UploadedDocument,
    ParsedSection,
    QuotationExtraction,
    FinalConditionComparison
)
from app.models.v6.generated_output import GeneratedOutput
from app.models.v6.output_template import OutputTemplate
import hashlib

from app.models.domain import User, AuditLog
from app.api.auth import get_current_user, get_current_active_user, verify_case_access, require_role
from app.api.exceptions import NotFoundException, ConflictException
from app.services.v6.lifecycle_guard import ensure_case_mutable
from pydantic import BaseModel
from datetime import datetime, timezone

from app.schemas.cases import (
    CaseCreate,
    CaseResponse,
    SectionUpdate,
    SectionResponse
)

from app.services.job_repository import JobRepository
from app.services.extraction.quotation_parser import parse_quotation_pdf
from app.services.extraction.requirement_condition_extractor import extract_requirement_conditions
from app.services.comparison.comparison_engine import run_comparison
from app.services.generation.html_generator import generate_html
from app.services.generation.plain_text_generator import generate_plain_text
from app.worker.quotation_tasks import process_quotation_task
from app.worker.comparison_tasks import process_comparison_task


router = APIRouter()


# =========================================================
# CASOS
# =========================================================

@router.post("/", response_model=CaseResponse, dependencies=[Depends(require_role(["ADMIN", "OPERATOR", "SUPERVISOR"]))])
def create_case(
    case: CaseCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):

    db_case = CaseFile(
        title=case.title,
        contract_type=case.contract_type,
        status="CREATED",
        tenant_id=current_user.tenant_id,
        created_by=current_user.id,
        assigned_to_user_id=current_user.id
    )

    db.add(db_case)
    db.commit()
    db.refresh(db_case)

    return db_case


@router.get("/", response_model=List[CaseResponse])
def get_cases(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    query = db.query(CaseFile).filter(CaseFile.tenant_id == current_user.tenant_id)
    if current_user.role != "ADMIN":
        query = query.filter(CaseFile.assigned_to_user_id == current_user.id)
    cases = query.all()
    for c in cases:
        if c.status == "ERROR":
            doc = db.query(UploadedDocument).filter(
                UploadedDocument.case_id == c.id,
                UploadedDocument.document_type == "requirement"
            ).order_by(UploadedDocument.id.desc()).first()
            if doc and doc.processing_error:
                setattr(c, "last_processing_error", doc.processing_error)
    return cases



class CaseAssign(BaseModel):
    assigned_to_user_id: int

@router.post("/{case_id}/assign", response_model=CaseResponse)
def assign_case(
    case_id: int,
    assign_req: CaseAssign,
    db_case: CaseFile = Depends(verify_case_access),
    current_user: User = Depends(require_role(["ADMIN"])),
    db: Session = Depends(get_db)
):
    target_user = db.query(User).filter(
        User.id == assign_req.assigned_to_user_id,
        User.tenant_id == current_user.tenant_id
    ).first()
    if not target_user:
        raise NotFoundException("Target user not found")

    locked_case = (
        db.query(CaseFile)
        .filter(CaseFile.id == case_id)
        .populate_existing()
        .with_for_update()
        .first()
    )
    if not locked_case:
        raise NotFoundException("Case not found")
    ensure_case_mutable(locked_case)

    locked_case.assigned_to_user_id = assign_req.assigned_to_user_id
    locked_case.assigned_by_user_id = current_user.id
    locked_case.assigned_at = datetime.now(timezone.utc)

    audit = AuditLog(
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        action="ASSIGN_CASE",
        entity_type="CaseFile",
        entity_id=str(case_id),
        details=f"Assigned to {target_user.username}",
        status="SUCCESS"
    )
    db.add(audit)

    try:
        import sqlalchemy.exc
        db.flush()
        db.commit()
    except sqlalchemy.exc.SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Transaction failed")

    db.refresh(locked_case)
    return locked_case

@router.get("/{case_id}", response_model=CaseResponse)
def get_case(
    case_id: int,
    db_case: CaseFile = Depends(verify_case_access),
    db: Session = Depends(get_db)
):

    if db_case.status == "ERROR":
        doc = db.query(UploadedDocument).filter(
            UploadedDocument.case_id == case_id,
            UploadedDocument.document_type == "requirement"
        ).order_by(UploadedDocument.id.desc()).first()
        if doc and doc.processing_error:
            setattr(db_case, "last_processing_error", doc.processing_error)

    return db_case



# =========================================================
# REQUERIMIENTO PDF + RQ
# =========================================================

@router.post("/{case_id}/requirement/upload", dependencies=[Depends(require_role(["ADMIN", "OPERATOR", "SUPERVISOR"]))])
def upload_requirement(
    case_id: int,
    file: UploadFile = File(...),
    document_type: str = Form("requirement"),
    db_case: CaseFile = Depends(verify_case_access),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    ensure_case_mutable(db_case)
    from app.core.config import settings
    from app.core.write_control import DocumentWriteControl
    from pathlib import Path
    if DocumentWriteControl.is_write_frozen(Path(settings.UPLOADS_DIR)):
        raise HTTPException(
            status_code=503,
            detail="Fallo de control de escrituras (B2): Respaldo LAN en curso. Congelamiento activo de documentos."
        )

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are allowed"
        )


    storage = get_storage()
    file_id = f"{uuid.uuid4()}.pdf"

    file.file.seek(0)
    file_path = storage.put(
        tenant_id=current_user.tenant_id,
        document_id=file_id,
        file_stream=file.file
    )


    try:
        locked_case = (
            db.query(CaseFile)
            .filter(CaseFile.id == case_id)
            .populate_existing()
            .with_for_update()
            .first()
        )
        if not locked_case:
            raise NotFoundException("Case not found")
        ensure_case_mutable(locked_case)

        job_id = str(uuid.uuid4())

        document = UploadedDocument(
            case_id=case_id,
            document_type=document_type,
            original_filename=file.filename,
            stored_path=file_path,
            mime_type="application/pdf",
            processing_job_id=job_id,
            processing_status="queued"
        )

        db.add(document)
        locked_case.status = "PROCESSING_REQUIREMENT"
        db.commit()
    except Exception:
        try:
            storage.delete(file_path)
        except Exception:
            pass
        raise

    job = task_queue.enqueue(
        "app.worker.tasks.process_requirement_task",
        case_id,
        file_path,
        job_id=job_id
    )


    return {
        "message": "Requirement queued",
        "job_id": job.id
    }



@router.get("/{case_id}/documents/requirement/content")
def get_requirement_document_content(
    case_id: int,
    db_case: CaseFile = Depends(verify_case_access),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    # Selección determinista del documento (el más reciente/vigente)
    doc = (
        db.query(UploadedDocument)
        .filter(
            UploadedDocument.case_id == case_id,
            UploadedDocument.document_type == "requirement"
        )
        .order_by(UploadedDocument.id.desc())
        .first()
    )

    if not doc:
        raise NotFoundException("Requirement document not found for this case")

    storage = get_storage()

    uploads_dir = os.path.realpath(settings.UPLOADS_DIR)
    target_path = os.path.realpath(doc.stored_path)

    is_safe = target_path.startswith(uploads_dir + os.sep)

    if not is_safe or not storage.exists(doc.stored_path):
        # Registrar falla silenciosamente sin exponer ruta interna
        audit = AuditLog(
            user_id=current_user.id,
            tenant_id=current_user.tenant_id,
            action="READ_DOCUMENT_CONTENT_FAILED",
            entity_type="UploadedDocument",
            entity_id=str(doc.id),
            details="File missing or invalid path resolution",
            status="FAILED"
        )
        db.add(audit)
        db.commit()
        raise NotFoundException("Document physical file is not available")

    # Auditoría exitosa
    audit = AuditLog(
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        action="READ_DOCUMENT_CONTENT",
        entity_type="UploadedDocument",
        entity_id=str(doc.id),
        details="Downloaded requirement PDF",
        status="SUCCESS"
    )
    db.add(audit)
    db.commit()

    safe_filename = f"requirement-{case_id}.pdf"

    return FileResponse(
        path=doc.stored_path,
        media_type="application/pdf",
        filename=safe_filename,
        content_disposition_type="inline",
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff"
        }
    )

# =========================================================
# ESTADO DEL JOB (PostgreSQL SSOT + Fallback Redis)
# =========================================================

@router.get("/jobs/{job_id}")
def get_job_status(
    job_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    # 1. Consultar PostgreSQL primero vía JobRepository (SSOT V5.3)
    job = JobRepository.get_by_job_id(
        db=db,
        job_id=job_id,
        tenant_id=current_user.tenant_id
    )

    if job:
        case_status = None
        if job.case_id:
            case = (
                db.query(CaseFile)
                .filter(
                    CaseFile.id == job.case_id,
                    CaseFile.tenant_id == current_user.tenant_id
                )
                .first()
            )
            if not case:
                raise NotFoundException("Job not found")
            if current_user.role != "ADMIN" and case.assigned_to_user_id != current_user.id:
                raise NotFoundException("Job not found")
            case_status = case.status

        result_summary = None
        if job.result_summary:
            try:
                result_summary = json.loads(job.result_summary)
            except Exception:
                result_summary = job.result_summary

        return {
            "job_id": job.job_id,
            "status": job.status,
            "progress": job.progress,
            "message": job.status_message or ("En cola" if job.status == "QUEUED" else job.status),
            "case_status": case_status,
            "error_message": job.error_message,
            "result_summary": result_summary
        }

    # 2. Fallback a RQ / Redis (Jobs OCR existentes de V5.2.1 / V1)
    try:
        rq_job = rq.job.Job.fetch(
            job_id,
            connection=task_queue.connection
        )

        document = (
            db.query(UploadedDocument)
            .filter(
                UploadedDocument.processing_job_id == job_id
            )
            .first()
        )
        if not document:
            raise NotFoundException("Job not found")

        case = (
            db.query(CaseFile)
            .filter(
                CaseFile.id == document.case_id,
                CaseFile.tenant_id == current_user.tenant_id
            )
            .first()
        )
        if not case:
            raise NotFoundException("Job not found")

        if current_user.role != "ADMIN" and case.assigned_to_user_id != current_user.id:
            raise NotFoundException("Job not found")

        return {
            "job_id": rq_job.id,
            "status": rq_job.get_status(),
            "progress": rq_job.meta.get(
                "progress",
                0
            ),
            "message": rq_job.meta.get(
                "status_message",
                "En cola"
            ),
            "case_status": case.status
        }

    except (rq.exceptions.NoSuchJobError, Exception):
        raise HTTPException(
            status_code=404,
            detail="Job not found"
        )



# =========================================================
# SECCIONES OCR
# =========================================================

@router.get(
    "/{case_id}/sections",
    response_model=List[SectionResponse]
)
def get_sections(
    case_id: int,
    db_case: CaseFile = Depends(verify_case_access),
    db: Session = Depends(get_db)
):

    return (
        db.query(ParsedSection)
        .filter(
            ParsedSection.case_id == case_id
        )
        .order_by(
            ParsedSection.original_order
        )
        .all()
    )



@router.put(
    "/sections/{section_id}",
    response_model=SectionResponse
)
def update_section(
    section_id: int,
    section_in: SectionUpdate,
    current_user: User = Depends(require_role(["ADMIN", "OPERATOR", "SUPERVISOR"])),
    db: Session = Depends(get_db)
):

    section = (
        db.query(ParsedSection)
        .filter(
            ParsedSection.id == section_id
        )
        .first()
    )


    if not section:
        raise HTTPException(
            status_code=404,
            detail="Section not found"
        )

    # Secure case resolution respecting tenant isolation and assignment
    case_query = db.query(CaseFile).filter(
        CaseFile.id == section.case_id,
        CaseFile.tenant_id == current_user.tenant_id
    )
    if current_user.role != "ADMIN":
        case_query = case_query.filter(CaseFile.assigned_to_user_id == current_user.id)
    case = case_query.populate_existing().with_for_update().first()
    if not case:
        raise NotFoundException("Section not found")

    ensure_case_mutable(case)

    section.is_selected = section_in.is_selected
    section.review_status = section_in.review_status
    section.current_text = section_in.current_text


    db.commit()
    db.refresh(section)


    return section

def has_unresolved_review(section: ParsedSection) -> bool:
    if section.review_status == "pending_review":
        return True

    # If a section was marked as MANUAL_REQUIRED or LOW_CONFIDENCE but hasn't been human-validated
    if section.review_status != "validated" and section.warnings_json:
        if any(w.get("code") in ("MANUAL_REQUIRED", "LOW_CONFIDENCE_TABLE", "LOW_CONFIDENCE_TITLE") for w in section.warnings_json):
            return True

    return False

@router.post(
    "/{case_id}/sections/confirm",
    response_model=CaseResponse
)
def confirm_sections(
    case_id: int,
    case: CaseFile = Depends(verify_case_access),
    current_user: User = Depends(require_role(["ADMIN", "OPERATOR", "SUPERVISOR"])),
    db: Session = Depends(get_db)
):
    locked_case = (
        db.query(CaseFile)
        .filter(CaseFile.id == case_id)
        .populate_existing()
        .with_for_update()
        .first()
    )
    if not locked_case:
        raise NotFoundException("Case not found")
    ensure_case_mutable(locked_case)

    if locked_case.status != "REVIEW_SECTIONS":
        raise HTTPException(status_code=400, detail="El expediente no está en revisión de secciones")

    sections = db.query(ParsedSection).filter(ParsedSection.case_id == case_id).all()
    if not sections:
        raise HTTPException(status_code=400, detail="No hay secciones para confirmar")

    pending_sections = [s for s in sections if has_unresolved_review(s)]
    if pending_sections:
        raise HTTPException(status_code=400, detail=f"Hay {len(pending_sections)} secciones con problemas no resueltos. Por favor revise y valide manualmente las secciones requeridas.")

    locked_case.status = "WAITING_QUOTATION"
    db.commit()
    db.refresh(locked_case)
    return locked_case



# =========================================================
# COTIZACION
# =========================================================

@router.post("/{case_id}/quotation/upload")
def upload_quotation(
    case_id: int,
    file: UploadFile = File(...),
    case: CaseFile = Depends(verify_case_access),
    current_user: User = Depends(require_role(["ADMIN", "OPERATOR", "SUPERVISOR"])),
    db: Session = Depends(get_db)
):
    ensure_case_mutable(case)

    # FLUJO ASÍNCRONO V5.3 (Feature Flag ON)
    if settings.is_async_quotation_enabled():
        storage = get_storage()
        file_ext = Path(file.filename or "quotation.pdf").suffix or ".pdf"
        saved_filename = f"quotation_{case_id}_{uuid.uuid4().hex}{file_ext}"

        file.file.seek(0)
        saved_path = storage.put(
            tenant_id=current_user.tenant_id,
            document_id=saved_filename,
            file_stream=file.file
        )

        try:
            locked_case = (
                db.query(CaseFile)
                .filter(CaseFile.id == case_id)
                .populate_existing()
                .with_for_update()
                .first()
            )
            if not locked_case:
                raise NotFoundException("Case not found")
            ensure_case_mutable(locked_case)

            # 1. Crear ProcessingJob en PostgreSQL antes de encolar
            job = JobRepository.create_job(
                db=db,
                case_id=case_id,
                tenant_id=current_user.tenant_id,
                user_id=current_user.id,
                job_type="QUOTATION_EXTRACTION"
            )
            db.commit()
        except Exception:
            try:
                storage.delete(saved_path)
            except Exception:
                pass
            raise

        # 2. Encolar en RQ (Worker de cotización por dominio)
        task_queue.enqueue(
            process_quotation_task,
            job_id=job.job_id,
            case_id=case_id,
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            file_path=saved_path
        )

        # 3. Retornar inmediatamente sin ejecutar OCR/extracción en el request
        return {
            "job_id": job.job_id,
            "status": "QUEUED",
            "message": "Quotation processing queued"
        }

    # FLUJO SÍNCRONO V5.2.1 (Fallback cuando Feature Flag está inactiva)
    with tempfile.NamedTemporaryFile(
        delete=False,
        suffix=".pdf"
    ) as temp:
        temp.write(
            file.file.read()
        )
        temp_path = temp.name

    try:
        quotation_data = parse_quotation_pdf(
            temp_path
        )

        locked_case = (
            db.query(CaseFile)
            .filter(CaseFile.id == case_id)
            .populate_existing()
            .with_for_update()
            .first()
        )
        if not locked_case:
            raise NotFoundException("Case not found")
        ensure_case_mutable(locked_case)

        quotation = QuotationExtraction(
            case_id=case_id,
            raw_json=quotation_data,
            review_status=(
                "validated"
                if quotation_data.get(
                    "global_confidence",
                    0
                ) > 0.8
                else "pending_review"
            )
        )

        db.add(quotation)
        locked_case.status = "COMPARING"
        db.commit()
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

    return {
        "message": "Quotation processed"
    }


# =========================================================
# COMPARACION
# =========================================================

@router.post("/{case_id}/comparison/run")
def run_comparison_endpoint(
    case_id: int,
    case: CaseFile = Depends(verify_case_access),
    current_user: User = Depends(require_role(["ADMIN", "OPERATOR", "SUPERVISOR"])),
    db: Session = Depends(get_db)
):
    ensure_case_mutable(case)

    # Re-fetch with row-level lock and populate_existing to prevent reading stale identity map data
    locked_case = (
        db.query(CaseFile)
        .filter(CaseFile.id == case_id)
        .populate_existing()
        .with_for_update()
        .first()
    )

    if not locked_case:
        raise HTTPException(status_code=404, detail="Case not found")

    # Count existing results
    existing_comparisons = (
        db.query(FinalConditionComparison)
        .filter(FinalConditionComparison.case_id == case_id)
        .count()
    )

    # Idempotent return if already completed
    if locked_case.status == "READY_GENERATE":
        if existing_comparisons > 0:
            return {
                "message": "Comparison already completed",
                "already_completed": True
            }
        else:
            raise HTTPException(
                status_code=409,
                detail="Inconsistent state: case is READY_GENERATE but no comparison results exist."
            )

    # Reject if not in COMPARING status
    if locked_case.status != "COMPARING":
        raise HTTPException(
            status_code=409,
            detail=f"Case is not ready for comparison. Current status: {locked_case.status}"
        )

    # Check for inconsistent state (COMPARING but results exist)
    if existing_comparisons > 0:
        raise HTTPException(
            status_code=409,
            detail="Inconsistent state: case is in COMPARING status but comparison results already exist."
        )

    quotation = (
        db.query(QuotationExtraction)
        .filter(
            QuotationExtraction.case_id == case_id
        )
        .first()
    )

    if not quotation:
        raise HTTPException(
            status_code=400,
            detail="Quotation missing"
        )

    # FLUJO ASÍNCRONO V5.3 (Feature Flag ON)
    if settings.is_async_comparison_enabled():
        # 1. Crear ProcessingJob en PostgreSQL antes de encolar
        job = JobRepository.create_job(
            db=db,
            case_id=case_id,
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            job_type="COMPARISON_RUN"
        )

        # 2. Encolar en Redis RQ (Worker por dominio)
        task_queue.enqueue(
            process_comparison_task,
            job_id=job.job_id,
            case_id=case_id,
            tenant_id=current_user.tenant_id,
            user_id=current_user.id
        )

        # 3. Retornar inmediatamente sin ejecutar el motor en el request
        return {
            "job_id": job.job_id,
            "status": "QUEUED",
            "message": "Comparison processing queued",
            "already_completed": False
        }

    # FLUJO SÍNCRONO V5.2.1 (Fallback cuando Feature Flag está inactiva)
    sections = (
        db.query(ParsedSection)
        .filter(
            ParsedSection.case_id == case_id,
            ParsedSection.is_selected == True
        )
        .all()
    )

    requirement_data = extract_requirement_conditions(sections)
    quotation_data = quotation.raw_json or {}

    from app.api.routing import TenantRouter

    route_info = TenantRouter.get_tenant_routing(locked_case.tenant_id, db)

    if route_info["engine"] == "v2":
        # Note: V2 Engine logic would be invoked here.
        pass

    try:
        results = run_comparison(
            requirement_data,
            quotation_data
        )

        for result in results:
            db.add(
                FinalConditionComparison(
                    case_id=case_id,
                    **result
                )
            )

        # Flush to catch any insertion errors before committing
        db.flush()

        locked_case.status = "READY_GENERATE"
        db.commit()

        return {
            "message": "Comparison completed",
            "already_completed": False
        }
    except Exception as e:
        db.rollback()
        # In a real app we'd log the exception here
        raise HTTPException(
            status_code=500,
            detail="An error occurred during comparison generation"
        )

@router.get("/{case_id}/comparison")
def get_comparison(
    case_id: int,
    case: CaseFile = Depends(verify_case_access),
    db: Session = Depends(get_db)
):
    comparisons = (
        db.query(FinalConditionComparison)
        .filter(FinalConditionComparison.case_id == case_id)
        .all()
    )
    return comparisons

# =========================================================
# GENERACION
# =========================================================

@router.post("/{case_id}/generate/html")
def generate_html_endpoint(
    case_id: int,
    case: CaseFile = Depends(verify_case_access),
    current_user: User = Depends(require_role(["ADMIN", "OPERATOR", "SUPERVISOR"])),
    db: Session = Depends(get_db)
):

    sections = (
        db.query(ParsedSection)
        .filter(
            ParsedSection.case_id == case_id,
            ParsedSection.is_selected == True
        )
        .all()
    )


    comparisons = (
        db.query(FinalConditionComparison)
        .filter(
            FinalConditionComparison.case_id == case_id
        )
        .all()
    )


    section_data = [

        {
            "title": s.title,
            "text": s.current_text,
            "roman": s.original_roman,
            "structure_json": s.structure_json
        }

        for s in sections
    ]



    comparison_data = [

        {
            "field_name": c.field_name,
            "requirement_value": c.requirement_value,
            "quotation_value": c.quotation_value,
            "final_value": c.final_value,
            "status": c.status
        }

        for c in comparisons
    ]



    html = generate_html(
        section_data,
        comparison_data
    )


    plain = generate_plain_text(
        section_data,
        comparison_data
    )



    last = (
        db.query(GeneratedOutput)
        .filter(
            GeneratedOutput.case_id == case_id
        )
        .order_by(
            GeneratedOutput.version_number.desc()
        )
        .first()
    )


    version = (
        last.version_number + 1
        if last else 1
    )


        # V6 compatibility: GeneratedOutput requires a provisioned active template.
    # OutputTemplate provisioning belongs to bootstrap/seed, not this endpoint.
    template = (
        db.query(OutputTemplate)
        .filter(
            OutputTemplate.type == "CONDICIONES",
            OutputTemplate.version == "1.0",
            OutputTemplate.entity_name == "Abast-gp",
            OutputTemplate.status == "ACTIVE",
        )
        .first()
    )

    if not template:
        raise HTTPException(
            status_code=500,
            detail="Mandatory active output template CONDICIONES/1.0 is not configured",
        )

    content_hash = hashlib.sha256(html.encode("utf-8")).hexdigest()

    output = GeneratedOutput(
        case_id=case_id,
        template_id=template.id,
        content_rendered=html,
        generation_hash=content_hash,
        generated_by=current_user.id,
        template_version=template.version,
        accuracy_gate_result="LEGACY_COMPAT",
        source_snapshot={
            "sections": section_data,
            "comparisons": comparison_data,
        },
        status="GENERATED",
        html_output=html,
        plain_text_output=plain,
        version_number=version,
    )

    db.add(output)

    db.commit()

    return {
        "message": "Generated",
        "version": version
    }

@router.get("/{case_id}/output")
def get_output(
    case_id: int,
    case: CaseFile = Depends(verify_case_access),
    db: Session = Depends(get_db)
):
    last_output = (
        db.query(GeneratedOutput)
        .filter(GeneratedOutput.case_id == case_id)
        .order_by(GeneratedOutput.version_number.desc())
        .first()
    )
    if not last_output:
        raise HTTPException(status_code=404, detail="Output not found")

    return {
        "html": last_output.html_output,
        "plain_text": last_output.plain_text_output,
        "version": last_output.version_number
    }