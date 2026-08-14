from sqlalchemy.orm import Session
from app.services.v6.telemetry.telemetry_worker import InstitutionalTelemetryWorker
from app.models.v6.tenant_config import TenantConfiguration
from typing import List

class InstitutionalTelemetryScheduler:
    """
    Mock integration for Celery Beat or External Cron.
    This class is called once a week by the infrastructure scheduler.
    """
    def __init__(self, db: Session):
        self.db = db
        
    def run_weekly_job(self) -> List[int]:
        """
        Iterates over all tenants and triggers the worker if Opt-In is enabled.
        Returns the list of Tenant IDs processed.
        """
        processed = []
        # Get all distinct tenants
        tenants = self.db.query(TenantConfiguration.tenant_id).all()
        
        for (tenant_id,) in tenants:
            worker = InstitutionalTelemetryWorker(self.db)
            event = worker.generate_weekly_snapshot(tenant_id)
            if event:
                processed.append(tenant_id)
                
        return processed
