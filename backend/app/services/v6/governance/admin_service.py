from sqlalchemy.orm import Session
from app.models.v6.tenant_config import TenantConfiguration
from app.models.domain import AuditLog
from typing import Any, Dict
from fastapi import HTTPException

class AdminGovernanceService:
    def __init__(self, db: Session):
        self.db = db

    def get_configuration(self, tenant_id: str) -> TenantConfiguration:
        config = self.db.query(TenantConfiguration).filter_by(tenant_id=tenant_id).first()
        if not config:
            config = TenantConfiguration(tenant_id=tenant_id)
            self.db.add(config)
            self.db.commit()
        return config

    def update_configuration(self, user_id: int, tenant_id: str, updates: Dict[str, Any]) -> TenantConfiguration:
        config = self.get_configuration(tenant_id)
        
        for key, new_value in updates.items():
            if not hasattr(config, key):
                continue
                
            old_value = getattr(config, key)
            if old_value != new_value:
                setattr(config, key, new_value)
                
                # Audit the change
                audit_action = "TELEMETRY_OPT_IN_GRANTED" if key == "telemetry_opt_in" and new_value is True else "CONFIG_CHANGED"
                if key == "telemetry_opt_in" and new_value is False:
                    audit_action = "TELEMETRY_OPT_IN_REVOKED"
                    
                audit = AuditLog(
                    user_id=user_id,
                    tenant_id=tenant_id,
                    action=audit_action,
                    entity_type="TenantConfiguration",
                    entity_id=str(config.id),
                    details=f"Field: {key} | Old: {old_value} | New: {new_value}",
                    status="PASSED"
                )
                self.db.add(audit)
                
        self.db.commit()
        self.db.refresh(config)
        return config
