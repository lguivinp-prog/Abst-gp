from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.api.auth import get_current_active_user, verify_case_access, require_role
from app.models.domain import User, CaseFile, AuditLog, UploadedDocument
from app.services.v6.evaluation.offer_evaluation_service import OfferEvaluationService
from app.models.v6.supplier_offer import SupplierOffer
from app.models.v6.case_requirement_matrix import CaseRequirementMatrix
from app.models.v6.offer_evidence import OfferEvidence
from app.models.v6.offer_requirement_evidence import OfferRequirementEvidence
from app.services.v6.quotation_guard import ensure_requirement_review_valid
from app.services.v6.lifecycle_guard import ensure_case_mutable
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timezone
import json

router = APIRouter()
evaluation_service = OfferEvaluationService()

def ensure_not_under_approval(case: CaseFile):
    """
    Prevents modifying evidence or re-evaluating when an approval is in progress.
    """
    if case.status == "UNDER_REVIEW":
        raise HTTPException(
            status_code=400,
            detail="Cannot modify evidence or evaluate offer while selection approval is in progress"
        )

class EvaluationResponse(BaseModel):
    id: int
    supplier_offer_id: int
    requirement_id: int
    status: str
    explanation: Optional[str] = None
    evaluation_confidence: Optional[float] = None
    requirement_description: Optional[str] = None
    requirement_type: Optional[str] = None
    validated_by: Optional[int] = None
    validated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class EvaluationUpdate(BaseModel):
    status: str
    explanation: str

@router.get("/cases/{case_id}/evaluations", response_model=List[EvaluationResponse])
def get_case_evaluations(
    case_id: int,
    case: CaseFile = Depends(verify_case_access),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from app.models.v6.offer_evaluation import OfferEvaluation
    # Get all offers for the case
    offers = db.query(SupplierOffer).filter(SupplierOffer.case_id == case_id).all()
    offer_ids = [offer.id for offer in offers]

    if not offer_ids:
        return []

    evals = db.query(OfferEvaluation).filter(OfferEvaluation.supplier_offer_id.in_(offer_ids)).all()
    # Populate extra fields from relationship
    for ev in evals:
        if ev.requirement:
            ev.requirement_description = ev.requirement.description
            ev.requirement_type = ev.requirement.requirement_type
    return evals

@router.post("/cases/{case_id}/offers/{offer_id}/evaluate", response_model=List[EvaluationResponse])
def evaluate_offer(
    case_id: int,
    offer_id: int,
    case: CaseFile = Depends(verify_case_access),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    ensure_case_mutable(case)
    ensure_not_under_approval(case)
    ensure_requirement_review_valid(case)

    # Verify offer belongs to case
    offer = db.query(SupplierOffer).filter(
        SupplierOffer.id == offer_id,
        SupplierOffer.case_id == case_id
    ).first()

    if not offer:
        raise HTTPException(status_code=403, detail="Offer does not belong to this case")

    # Check if offer is actually an offer (has a price or document)
    if offer.status == "PENDING" and offer.price is None and offer.source_document is None:
        raise HTTPException(status_code=400, detail="Cannot evaluate incomplete offer")

    # ETAPA 3: In-place atomic and idempotent evaluation without pre-delete
    evals = evaluation_service.evaluate_offer(
        db=db,
        supplier_offer_id=offer_id,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id
    )
    for ev in evals:
        if ev.requirement:
            ev.requirement_description = ev.requirement.description
            ev.requirement_type = ev.requirement.requirement_type
    return evals

@router.get("/cases/{case_id}/offers/{offer_id}/evaluations", response_model=List[EvaluationResponse])
def get_offer_evaluations(
    case_id: int,
    offer_id: int,
    case: CaseFile = Depends(verify_case_access),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from app.models.v6.offer_evaluation import OfferEvaluation
    # Verify offer belongs to case
    offer = db.query(SupplierOffer).filter(
        SupplierOffer.id == offer_id,
        SupplierOffer.case_id == case_id
    ).first()

    if not offer:
        raise HTTPException(status_code=403, detail="Offer does not belong to this case")

    evals = db.query(OfferEvaluation).filter(OfferEvaluation.supplier_offer_id == offer_id).all()
    for ev in evals:
        if ev.requirement:
            ev.requirement_description = ev.requirement.description
            ev.requirement_type = ev.requirement.requirement_type
    return evals

@router.put("/cases/{case_id}/evaluations/{eval_id}", response_model=EvaluationResponse)
def update_evaluation(
    case_id: int,
    eval_id: int,
    update_data: EvaluationUpdate,
    current_user: User = Depends(require_role(["ADMIN", "SUPERVISOR", "OPERATOR"])),
    case: CaseFile = Depends(verify_case_access),
    db: Session = Depends(get_db)
):
    ensure_case_mutable(case)
    ensure_not_under_approval(case)
    ensure_requirement_review_valid(case)

    # CONTROL 3: Operador sin asignación queda rechazado
    if current_user.role == "OPERATOR" and case.assigned_to_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Operator not authorized to modify evaluation for unassigned case")

    from app.models.v6.offer_evaluation import OfferEvaluation
    eval_entry = db.query(OfferEvaluation).filter(OfferEvaluation.id == eval_id).first()
    if not eval_entry:
        raise HTTPException(status_code=404, detail="Evaluation not found")

    # Verify it belongs to case
    offer = db.query(SupplierOffer).filter(
        SupplierOffer.id == eval_entry.supplier_offer_id,
        SupplierOffer.case_id == case_id
    ).first()

    if not offer:
        raise HTTPException(status_code=403, detail="Evaluation does not belong to this case")

    try:
        updated = evaluation_service.update_evaluation(
            db=db,
            eval_id=eval_id,
            new_status=update_data.status,
            explanation=update_data.explanation,
            user_id=current_user.id,
            tenant_id=current_user.tenant_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not updated:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    if updated.requirement:
        updated.requirement_description = updated.requirement.description
        updated.requirement_type = updated.requirement.requirement_type
    return updated

# --- P12 Evidence Traceability Schemas & Endpoints ---

class RequirementEvidenceCreate(BaseModel):
    offer_evidence_id: int
    document_id: Optional[int] = None
    source_document: Optional[str] = None
    page: Optional[int] = None
    fragment: Optional[str] = None
    notes: Optional[str] = None

class RequirementEvidenceReview(BaseModel):
    verification_status: str # VERIFIED, REJECTED, OBSERVED, PENDING
    notes: Optional[str] = None

class RequirementEvidenceResponse(BaseModel):
    id: int
    case_id: int
    supplier_offer_id: int
    requirement_id: int
    offer_evidence_id: int
    document_id: Optional[int] = None
    source_document: Optional[str] = None
    page: Optional[int] = None
    fragment: Optional[str] = None
    verification_status: str
    verified_by: Optional[int] = None
    verified_by_username: Optional[str] = None
    verified_at: Optional[datetime] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

@router.get("/cases/{case_id}/evidence", response_model=List[RequirementEvidenceResponse])
def get_case_requirement_evidence(
    case_id: int,
    supplier_offer_id: Optional[int] = None,
    requirement_id: Optional[int] = None,
    case: CaseFile = Depends(verify_case_access),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    query = db.query(OfferRequirementEvidence).filter(OfferRequirementEvidence.case_id == case_id)
    if supplier_offer_id is not None:
        query = query.filter(OfferRequirementEvidence.supplier_offer_id == supplier_offer_id)
    if requirement_id is not None:
        query = query.filter(OfferRequirementEvidence.requirement_id == requirement_id)

    items = query.all()
    for itm in items:
        if itm.verifier:
            itm.verified_by_username = itm.verifier.username
    return items

@router.get("/cases/{case_id}/offers/{offer_id}/requirements/{requirement_id}/evidence", response_model=List[RequirementEvidenceResponse])
def get_offer_requirement_evidence(
    case_id: int,
    offer_id: int,
    requirement_id: int,
    case: CaseFile = Depends(verify_case_access),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    offer = db.query(SupplierOffer).filter(SupplierOffer.id == offer_id, SupplierOffer.case_id == case_id).first()
    if not offer:
        raise HTTPException(status_code=404, detail="Offer not found in this case")

    req = db.query(CaseRequirementMatrix).filter(CaseRequirementMatrix.id == requirement_id, CaseRequirementMatrix.case_id == case_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Requirement not found in this case")

    items = db.query(OfferRequirementEvidence).filter(
        OfferRequirementEvidence.case_id == case_id,
        OfferRequirementEvidence.supplier_offer_id == offer_id,
        OfferRequirementEvidence.requirement_id == requirement_id
    ).all()
    for itm in items:
        if itm.verifier:
            itm.verified_by_username = itm.verifier.username
    return items

@router.post("/cases/{case_id}/offers/{offer_id}/requirements/{requirement_id}/evidence", response_model=RequirementEvidenceResponse)
def link_requirement_evidence(
    case_id: int,
    offer_id: int,
    requirement_id: int,
    data: RequirementEvidenceCreate,
    current_user: User = Depends(require_role(["ADMIN", "SUPERVISOR", "OPERATOR"])),
    case: CaseFile = Depends(verify_case_access),
    db: Session = Depends(get_db)
):
    ensure_case_mutable(case)
    ensure_not_under_approval(case)
    ensure_requirement_review_valid(case)

    # CONTROL 3: Operador sin asignación queda rechazado
    if current_user.role == "OPERATOR" and case.assigned_to_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Operator not authorized to link evidence for unassigned case")

    offer = db.query(SupplierOffer).filter(SupplierOffer.id == offer_id, SupplierOffer.case_id == case_id).first()
    if not offer:
        raise HTTPException(status_code=404, detail="Offer not found in this case")

    req = db.query(CaseRequirementMatrix).filter(CaseRequirementMatrix.id == requirement_id, CaseRequirementMatrix.case_id == case_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Requirement not found in this case")

    offer_ev = db.query(OfferEvidence).filter(OfferEvidence.id == data.offer_evidence_id, OfferEvidence.supplier_offer_id == offer_id).first()
    if not offer_ev:
        raise HTTPException(status_code=400, detail="Offer evidence does not belong to this offer")

    # CORRECCIÓN 1: Exigir documento fuente verificable existente en el expediente
    target_doc_id = data.document_id or offer_ev.document_id
    if not target_doc_id:
        raise HTTPException(status_code=400, detail="A valid, verifiable UploadedDocument is required to link evidence")

    doc = db.query(UploadedDocument).filter(UploadedDocument.id == target_doc_id, UploadedDocument.case_id == case_id).first()
    if not doc:
        raise HTTPException(status_code=400, detail="Source document not found or does not belong to this case")

    # Comprobar correspondencia entre el documento de OfferEvidence y el documento vinculado
    if offer_ev.document_id is not None and offer_ev.document_id != target_doc_id:
        raise HTTPException(status_code=400, detail="Document mismatch between offer evidence and requirement link")

    if offer_ev.document_id is None:
        offer_ev.document_id = doc.id

    # Check unique constraint (requirement_id, offer_evidence_id)
    existing = db.query(OfferRequirementEvidence).filter_by(
        requirement_id=requirement_id,
        offer_evidence_id=data.offer_evidence_id
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="This evidence is already linked to this requirement")

    # Fuente documental obtenida del registro real, fragmento original protegido contra sustitución
    src_doc = doc.original_filename
    page = offer_ev.page if offer_ev.page is not None else data.page
    fragment = offer_ev.fragment

    # Los fragmentos manuales se registran como anotaciones en notas, no como prueba documental originaria
    notes_val = data.notes or ""
    if data.fragment and data.fragment.strip() != (offer_ev.fragment or "").strip():
        annotation = f"[Anotación: {data.fragment.strip()}]"
        notes_val = f"{notes_val}\n{annotation}".strip() if notes_val else annotation
    notes_final = notes_val if notes_val else None

    # CORRECCIÓN 2: Atomicidad de operación completa - Un solo commit al finalizar correctamente
    try:
        new_link = OfferRequirementEvidence(
            case_id=case_id,
            supplier_offer_id=offer_id,
            requirement_id=requirement_id,
            offer_evidence_id=data.offer_evidence_id,
            document_id=doc.id,
            source_document=src_doc,
            page=page,
            fragment=fragment,
            verification_status="PENDING",
            notes=notes_final
        )
        db.add(new_link)
        db.flush()

        # Reevaluación inmediata con auto_commit=False en la misma transacción
        evaluation_service.reevaluate_requirement(
            db, offer_id, requirement_id, current_user.id, current_user.tenant_id, auto_commit=False
        )

        audit = AuditLog(
            user_id=current_user.id,
            tenant_id=current_user.tenant_id,
            action="LINK_REQUIREMENT_EVIDENCE",
            entity_type="OfferRequirementEvidence",
            entity_id=str(new_link.id),
            details=json.dumps({"offer_id": offer_id, "requirement_id": requirement_id, "offer_evidence_id": data.offer_evidence_id}),
            status="SUCCESS"
        )
        db.add(audit)
        db.commit()
        db.refresh(new_link)
        if new_link.verifier:
            new_link.verified_by_username = new_link.verifier.username
        return new_link
    except Exception as e:
        db.rollback()
        raise e

@router.put("/cases/{case_id}/evidence/{evidence_link_id}/review", response_model=RequirementEvidenceResponse)
def review_requirement_evidence(
    case_id: int,
    evidence_link_id: int,
    data: RequirementEvidenceReview,
    current_user: User = Depends(require_role(["ADMIN", "SUPERVISOR", "OPERATOR"])),
    case: CaseFile = Depends(verify_case_access),
    db: Session = Depends(get_db)
):
    ensure_case_mutable(case)
    ensure_not_under_approval(case)

    # Role & Authorization check:
    # Operadores sin autorización no pueden validar evidencia ajena
    if current_user.role == "OPERATOR" and case.assigned_to_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Operator not authorized to review evidence for unassigned case")

    valid_statuses = {"VERIFIED", "REJECTED", "OBSERVED", "PENDING"}
    if data.verification_status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid verification status. Allowed: {valid_statuses}")

    evidence_link = db.query(OfferRequirementEvidence).filter(
        OfferRequirementEvidence.id == evidence_link_id,
        OfferRequirementEvidence.case_id == case_id
    ).first()
    if not evidence_link:
        raise HTTPException(status_code=404, detail="Evidence link not found in this case")

    # CORRECCIÓN 1: No permitir marcar VERIFIED sin documento fuente real y verificable
    if data.verification_status == "VERIFIED":
        if not evidence_link.document_id:
            raise HTTPException(status_code=400, detail="Cannot mark VERIFIED: Missing verifiable source document.")
        doc = db.query(UploadedDocument).filter(UploadedDocument.id == evidence_link.document_id, UploadedDocument.case_id == case_id).first()
        if not doc:
            raise HTTPException(status_code=400, detail="Cannot mark VERIFIED: Source document not found in this case.")
        oe = db.query(OfferEvidence).filter_by(id=evidence_link.offer_evidence_id, supplier_offer_id=evidence_link.supplier_offer_id).first()
        if not oe:
            raise HTTPException(status_code=400, detail="Cannot mark VERIFIED: Offer evidence not found.")
        if oe.document_id is not None and oe.document_id != evidence_link.document_id:
            raise HTTPException(status_code=400, detail="Cannot mark VERIFIED: Document mismatch between evidence and link.")

    # CORRECCIÓN 2: Atomicidad de operación completa
    try:
        evidence_link.verification_status = data.verification_status
        evidence_link.verified_by = current_user.id
        evidence_link.verified_at = datetime.now(timezone.utc)
        if data.notes is not None:
            evidence_link.notes = data.notes

        db.flush()

        # Re-evaluate requirement with updated evidence status (auto_commit=False)
        evaluation_service.reevaluate_requirement(
            db,
            evidence_link.supplier_offer_id,
            evidence_link.requirement_id,
            current_user.id,
            current_user.tenant_id,
            auto_commit=False
        )

        audit = AuditLog(
            user_id=current_user.id,
            tenant_id=current_user.tenant_id,
            action="REVIEW_REQUIREMENT_EVIDENCE",
            entity_type="OfferRequirementEvidence",
            entity_id=str(evidence_link.id),
            details=json.dumps({"verification_status": data.verification_status, "notes": data.notes}),
            status="SUCCESS"
        )
        db.add(audit)
        db.commit()
        db.refresh(evidence_link)
        if evidence_link.verifier:
            evidence_link.verified_by_username = evidence_link.verifier.username
        return evidence_link
    except Exception as e:
        db.rollback()
        raise e

@router.delete("/cases/{case_id}/evidence/{evidence_link_id}")
def unlink_requirement_evidence(
    case_id: int,
    evidence_link_id: int,
    current_user: User = Depends(require_role(["ADMIN", "SUPERVISOR", "OPERATOR"])),
    case: CaseFile = Depends(verify_case_access),
    db: Session = Depends(get_db)
):
    ensure_case_mutable(case)
    ensure_not_under_approval(case)

    # CONTROL 3: Operador sin asignación queda rechazado
    if current_user.role == "OPERATOR" and case.assigned_to_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Operator not authorized to unlink evidence for unassigned case")

    evidence_link = db.query(OfferRequirementEvidence).filter(
        OfferRequirementEvidence.id == evidence_link_id,
        OfferRequirementEvidence.case_id == case_id
    ).first()
    if not evidence_link:
        raise HTTPException(status_code=404, detail="Evidence link not found in this case")

    # CORRECCIÓN 2: Atomicidad de operación completa
    try:
        offer_id = evidence_link.supplier_offer_id
        req_id = evidence_link.requirement_id

        db.delete(evidence_link)
        db.flush()

        # Invalidate/reevaluate requirement: if no more evidence remains, status becomes MISSING_DATA
        evaluation_service.reevaluate_requirement(
            db,
            offer_id,
            req_id,
            current_user.id,
            current_user.tenant_id,
            auto_commit=False
        )

        audit = AuditLog(
            user_id=current_user.id,
            tenant_id=current_user.tenant_id,
            action="UNLINK_REQUIREMENT_EVIDENCE",
            entity_type="OfferRequirementEvidence",
            entity_id=str(evidence_link_id),
            details=json.dumps({"supplier_offer_id": offer_id, "requirement_id": req_id}),
            status="SUCCESS"
        )
        db.add(audit)
        db.commit()
        return {"status": "success", "message": "Evidence link removed"}
    except Exception as e:
        db.rollback()
        raise e

class ContractualConditionResponse(BaseModel):
    id: int
    supplier_offer_id: int
    key: Optional[str] = None
    label: Optional[str] = None
    required_value: Optional[str] = None
    offered_value: Optional[str] = None
    final_value: Optional[str] = None
    unit: Optional[str] = None
    resolution_rule: str
    status: str

    class Config:
        from_attributes = True

@router.get("/cases/{case_id}/evaluations/contractual", response_model=List[ContractualConditionResponse])
def get_contractual_evaluations(
    case_id: int,
    case: CaseFile = Depends(verify_case_access),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from app.services.v6.evaluation.contractual_resolver import ContractualResolver
    from app.models.v6.contractual_condition import ContractualCondition

    offers = db.query(SupplierOffer).filter(SupplierOffer.case_id == case_id).all()
    requirements = db.query(CaseRequirementMatrix).filter(CaseRequirementMatrix.case_id == case_id).all()

    resolver = ContractualResolver(db)
    all_conditions = []

    for offer in offers:
        existing = db.query(ContractualCondition).filter_by(supplier_offer_id=offer.id).all()
        
        if case.status in ["APPROVED", "COMPLETED"]:
            all_conditions.extend(existing)
            continue
            
        if existing:
            db.query(ContractualCondition).filter_by(supplier_offer_id=offer.id).delete()
            db.flush()

        conditions = resolver.resolve_offer(offer.id, requirements)
        all_conditions.extend(conditions)

    return all_conditions

class VFMResponse(BaseModel):
    supplier_offer_id: int
    supplier_id: int
    is_eligible: bool
    is_evaluated: Optional[bool] = None
    reason: Optional[str] = None
    total_score: Optional[float] = None
    price: Optional[float] = None
    vfm_ratio: Optional[float] = None

@router.get("/cases/{case_id}/evaluations/vfm", response_model=List[VFMResponse])
def get_vfm_ranking(
    case_id: int,
    case: CaseFile = Depends(verify_case_access),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from app.services.v6.evaluation.vfm_service import ValueForMoneyService

    vfm_service = ValueForMoneyService(db)
    results = vfm_service.calculate_vfm(case_id)
    return results
