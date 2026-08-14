from sqlalchemy.orm import Session
from app.models.v6.telemetry import InstitutionalTelemetryEvent
from app.models.v6.tenant_config import TenantConfiguration
from datetime import datetime

class InstitutionalTelemetryWorker:
    def __init__(self, db: Session):
        self.db = db
        self.policy_version = "v1.0"
        
    def generate_weekly_snapshot(self, tenant_id: str) -> InstitutionalTelemetryEvent:
        """
        Gathers only permitted metadata. Does NOT query CaseFile or Supplier models for PII.
        """
        config = self.db.query(TenantConfiguration).filter_by(tenant_id=tenant_id).first()
        
        # Security Gate: Opt-In validation
        if not config or not config.telemetry_opt_in:
            return None # Telemetry disabled by the institution
            
        # Mocking aggregated calculations for the prototype
        event = InstitutionalTelemetryEvent(
            tenant_id=tenant_id,
            system_version="6.0.1",
            avg_rag_latency_ms=1250.5,
            avg_ocr_latency_ms=850.0,
            total_cases_processed=42,
            total_supervisor_exceptions=3,
            blocked_by_quality_gate=12,
            api_fallback_events=1,
            rag_human_correction_rate=0.05,
            telemetry_policy_version=self.policy_version,
            opt_in_status=True
        )
        
        self.db.add(event)
        self.db.commit()
        return event
