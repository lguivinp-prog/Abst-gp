from sqlalchemy.orm import Session
from app.models.v6.validation_request import ValidationRequest
from app.models.domain import AuditLog
from .sunat_mock import SUNATMockProvider
import json

class ValidationService:
    @staticmethod
    def request_validation(db: Session, supplier_id: int, source: str, user_id: int, tenant_id: str) -> ValidationRequest:
        req = ValidationRequest(
            supplier_id=supplier_id,
            source=source,
            status="PENDING",
            requested_by=user_id
        )
        db.add(req)
        db.flush()
        
        audit = AuditLog(
            user_id=user_id,
            tenant_id=tenant_id,
            action="REQUEST_VALIDATION",
            entity_type="ValidationRequest",
            entity_id=str(req.id),
            details=json.dumps({"source": source}),
            status="SUCCESS"
        )
        db.add(audit)
        db.commit()
        db.refresh(req)
        
        # Here we would enqueue to RQ Worker: 
        # rq_queue.enqueue(process_validation_task, req.id)
        # For Sprint 3, since we need to prepare the architecture but execute it,
        # we will simulate the worker processing synchronously just for the API response
        # or leave it pending to be processed by a mock task runner.
        # Given "POST validate NO debe esperar respuesta. Debe: Crear ValidationRequest. Procesamiento asíncrono posterior."
        # We just return the PENDING request.
        return req
