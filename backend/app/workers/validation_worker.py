from app.core.database import SessionLocal
from app.services.v6.integrations.validation_orchestrator import SupplierValidationOrchestrator
# import celery_app ... (Mocked for architecture definition)

# @celery_app.task(name="trigger_external_validation")
def trigger_external_validation(supplier_id: int, user_id: int = None, fallback_evidence: dict = None):
    """
    Celery task that runs the SupplierValidationOrchestrator asynchronously.
    """
    db = SessionLocal()
    try:
        orchestrator = SupplierValidationOrchestrator()
        orchestrator.run_async_validation(db, supplier_id, user_id, fallback_evidence)
    finally:
        db.close()
