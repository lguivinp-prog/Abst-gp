from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from app.api.deps import get_db, require_admin_it, get_current_user
from app.models.domain import User
from app.services.v6.governance.admin_service import AdminGovernanceService
from app.models.v6.tenant_config import TenantConfigurationHistory

router = APIRouter()

@router.get("/config")
def get_tenant_configuration(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user) # Anyone in tenant can see the config (Read-Only)
):
    service = AdminGovernanceService(db)
    config = service.get_configuration(current_user.tenant_id)
    return config

@router.put("/config/thresholds")
def update_thresholds(
    min_dpi: int = Body(None),
    min_rag: int = Body(None),
    reason: str = Body(default="Ajuste Operativo"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_it) # Strict RBAC
):
    # Configuration Validation (No destructive values)
    if min_dpi is not None and (min_dpi < 72 or min_dpi > 600):
        raise HTTPException(status_code=400, detail="DPI threshold out of bounds (72-600)")
    if min_rag is not None and (min_rag < 50 or min_rag > 99):
        raise HTTPException(status_code=400, detail="RAG Confidence must be between 50 and 99")
        
    service = AdminGovernanceService(db)
    config = service.get_configuration(current_user.tenant_id)
    
    # Track version increment
    new_version = config.configuration_version + 1
    
    if min_dpi is not None and min_dpi != config.min_dpi_threshold:
        history = TenantConfigurationHistory(
            tenant_id=current_user.tenant_id, version=new_version, field_changed="min_dpi_threshold",
            old_value=str(config.min_dpi_threshold), new_value=str(min_dpi),
            changed_by_user_id=current_user.id, reason=reason
        )
        db.add(history)
        config.min_dpi_threshold = min_dpi
        
    if min_rag is not None and min_rag != config.min_rag_confidence:
        history = TenantConfigurationHistory(
            tenant_id=current_user.tenant_id, version=new_version, field_changed="min_rag_confidence",
            old_value=str(config.min_rag_confidence), new_value=str(min_rag),
            changed_by_user_id=current_user.id, reason=reason
        )
        db.add(history)
        config.min_rag_confidence = min_rag
        
    config.configuration_version = new_version
    db.commit()
    db.refresh(config)
    return {"status": "success", "new_version": new_version}

@router.put("/config/telemetry")
def update_telemetry_opt_in(
    opt_in: bool = Body(...),
    reason: str = Body(default="Política de Telemetría"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_it) # Strict RBAC
):
    service = AdminGovernanceService(db)
    config = service.get_configuration(current_user.tenant_id)
    
    if config.telemetry_opt_in != opt_in:
        new_version = config.configuration_version + 1
        history = TenantConfigurationHistory(
            tenant_id=current_user.tenant_id, version=new_version, field_changed="telemetry_opt_in",
            old_value=str(config.telemetry_opt_in), new_value=str(opt_in),
            changed_by_user_id=current_user.id, reason=reason
        )
        db.add(history)
        
        config.telemetry_opt_in = opt_in
        config.configuration_version = new_version
        db.commit()
        
    return {"status": "success", "opt_in": opt_in}
