from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import case, func
from app.api.deps import get_db, get_current_user
from app.models.v6.case_operational_snapshot import CaseOperationalSnapshot
from app.models.domain import AuditLog, User
from app.models.v6.supplier_profile import SupplierProfile
from app.models.v6.supplier_offer import SupplierOffer
from app.services.v6.export.supervisor_export_service import SupervisorExportService

router = APIRouter()

# Dependency for RBAC
def require_supervisor(current_user: User = Depends(get_current_user)):
    if current_user.role != "SUPERVISOR":
        raise HTTPException(status_code=403, detail="Solo los usuarios con rol SUPERVISOR pueden acceder a esta funcion.")
    return current_user

@router.get("/dashboard")
def get_dashboard(db: Session = Depends(get_db)):
    active = db.query(CaseOperationalSnapshot).count()
    high_risk = db.query(CaseOperationalSnapshot).filter(CaseOperationalSnapshot.risk_level == "HIGH").count()
    return {
        "active_cases": active,
        "high_risk_cases": high_risk
    }

@router.get("/queue")
def get_approval_queue(db: Session = Depends(get_db)):
    """
    Returns cases ordered by Risk (HIGH > MEDIUM > LOW)
    """
    risk_order = case(
        (CaseOperationalSnapshot.risk_level == 'HIGH', 1),
        (CaseOperationalSnapshot.risk_level == 'MEDIUM', 2),
        (CaseOperationalSnapshot.risk_level == 'LOW', 3),
        else_=4
    )
    
    snapshots = db.query(CaseOperationalSnapshot).order_by(risk_order).all()
    return snapshots

@router.get("/cases/{case_id}/summary")
def get_supplier_summary(case_id: int, db: Session = Depends(get_db)):
    # Assuming winner is the one with status SELECTED
    offer = db.query(SupplierOffer).filter_by(case_id=case_id, status="SELECTED").first()
    if not offer:
        raise HTTPException(status_code=404, detail="No selected supplier for this case")
        
    profile = db.query(SupplierProfile).filter_by(supplier_id=offer.supplier_id).first()
    
    # In a real impl, fetch the latest ValidationRequests for SUNAT, RNP, FUP, CIIU and Experience calculation trace
    return {
        "supplier_id": profile.supplier_id,
        "overall_validation": profile.validation_status,
        "sunat": "PASSED (mock)",
        "rnp": "PASSED (mock)",
        "fup": "PASSED (mock)",
        "ciiu": "WARNING (mock)",
        "experience": "PASSED (mock)"
    }

@router.get("/cases/{case_id}/timeline")
def get_audit_timeline(case_id: int, db: Session = Depends(get_db)):
    audits = db.query(AuditLog).filter_by(entity_type="CaseFile", entity_id=str(case_id)).order_by(AuditLog.timestamp.desc()).all()
    return audits

@router.get("/export/csv")
def export_csv(
    risk_level: str = Query(None),
    status: str = Query(None),
    start_date: str = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_supervisor) # RBAC Security Enforced
):
    service = SupervisorExportService(db)
    filters = {
        "risk_level": risk_level,
        "status": status,
        "start_date": start_date
    }
    
    generator = service.generate_csv_stream(current_user.id, current_user.tenant_id, filters)
    
    return StreamingResponse(
        generator,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=supervisor_analytics_export.csv"}
    )
