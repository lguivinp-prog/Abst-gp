from sqlalchemy.orm import Session
from app.models.v6.supplier_profile import SupplierProfile
from app.models.v6.validation_request import ValidationRequest
from app.models.v6.supplier import Supplier
from .providers.sunat_adapter import SUNATProvider
from .providers.rnp_adapter import RNPProvider
from .providers.fup_adapter import FUPProvider
from typing import Dict, Any

class SupplierValidationOrchestrator:
    def __init__(self):
        self.sunat = SUNATProvider()
        self.rnp = RNPProvider()
        self.fup = FUPProvider()
        
    def run_async_validation(self, db: Session, supplier_id: int, user_id: int = None, fallback_evidence: Dict[str, Dict[str, Any]] = None):
        """
        Orchestrates external validations asynchronously.
        fallback_evidence is a dict like {"SUNAT": {...}, "RNP": {...}, "FUP": {...}}
        In a real prod environment, this is called by a Celery task.
        """
        supplier = db.query(Supplier).filter_by(id=supplier_id).first()
        if not supplier:
            return
            
        profile = db.query(SupplierProfile).filter_by(supplier_id=supplier_id).first()
        if not profile:
            profile = SupplierProfile(
    supplier_id=supplier_id,
    status_summary="PENDING_VERIFICATION",
    validation_status="PENDING"
    )
            db.add(profile)
            db.flush()
            
        fallback = fallback_evidence or {}
        
        # Run validations
        sunat_res = self.sunat.validate(supplier.ruc, fallback.get("SUNAT"))
        rnp_res = self.rnp.validate(supplier.ruc, fallback.get("RNP"))
        fup_res = self.fup.validate(supplier.ruc, fallback.get("FUP"))
        
        # Create ValidationRequests
        for name, res in [("SUNAT", sunat_res), ("RNP", rnp_res), ("FUP", fup_res)]:
            req = ValidationRequest(
                supplier_id=supplier_id,
                source=name,
                status=res.status,
                requested_by=user_id,
                response_payload=res.payload,
                response_schema_version=res.schema_version,
                response_hash=res.hash
            )
            db.add(req)
            
        # Consolidate Supplier Profile Status
        statuses = [sunat_res.status, rnp_res.status, fup_res.status]

        if "ERROR" in statuses:
            summary_status = "ERROR"
            validation_status = "WARNING"
        elif "BLOCKED" in statuses:
            summary_status = "BLOCKED"
            validation_status = "BLOCKED"
        elif "MANUAL_REQUIRED" in statuses:
            summary_status = "MANUAL_REQUIRED"
            validation_status = "PARTIAL"
        elif "WARNING" in statuses:
            summary_status = "WARNING"
            validation_status = "WARNING"
        else:
            summary_status = "VERIFIED"
            validation_status = "VERIFIED"

        profile.status_summary = summary_status
        profile.validation_status = validation_status

        db.commit()
