from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from app.models.v6.supplier_profile import SupplierProfile
from app.models.v6.validation_request import ValidationRequest
from app.models.v6.supplier import Supplier
from .providers.sunat_adapter import SUNATProvider
from .providers.rnp_adapter import RNPProvider
from .providers.fup_adapter import FUPProvider
from .providers.ciiu_adapter import CIIUProvider
from typing import Dict, Any
from .providers.sunat_activities_provider import SunatActivitiesProvider

class SupplierValidationOrchestrator:
    def __init__(self):
        self.sunat = SUNATProvider()
        self.sunat_activities = SunatActivitiesProvider()
        self.rnp = RNPProvider()
        self.fup = FUPProvider()
        self.ciiu = CIIUProvider()

    def run_async_validation(self, db: Session, supplier_id: int, user_id: int = None, fallback_evidence: Dict[str, Dict[str, Any]] = None, case_id: int = None):
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
        sunat_act_res = self.sunat_activities.validate(supplier.ruc, fallback.get("SUNAT"))
        rnp_res = self.rnp.validate(supplier.ruc, fallback.get("RNP"))
        fup_res = self.fup.validate(supplier.ruc, fallback.get("FUP"))

        # Merge activities for CIIU
        if sunat_act_res.status == "PASSED" and sunat_act_res.payload and sunat_act_res.payload.get("actividades"):
            sunat_ciiu = sunat_act_res.payload["actividades"]
            activities_complete = sunat_act_res.payload.get("activities_complete", False)
        else:
            act_str = sunat_res.payload.get("actividad_reportada_decolecta") if sunat_res.payload else ""
            sunat_ciiu = [{"descripcion_sunat": act_str, "tipo": "PRINCIPAL"}] if act_str else []
            activities_complete = False

        # Retrieve expected keywords from some case context if possible, otherwise empty
        ciiu_res = self.ciiu.validate(db, sunat_ciiu, activities_complete, "")

        # Cross-Source Consistency Check
        decolecta_activity = sunat_res.payload.get("actividad_reportada_decolecta") if sunat_res.payload else None
        if decolecta_activity and sunat_act_res.payload and sunat_act_res.payload.get("activities"):
            migo_activities = sunat_act_res.payload["activities"]
            norm_dec = self.ciiu._normalize(decolecta_activity)
            match_count = sum(1 for m in migo_activities if self.ciiu._normalize(m.get("descripcion_sunat", "")) == norm_dec)
            is_consistent = match_count > 0

            sunat_act_res.payload["cross_source_consistency"] = is_consistent
            sunat_act_res.payload["cross_source_match_count"] = match_count
            sunat_act_res.payload["cross_source_status"] = "CONSISTENT" if is_consistent else "REVIEW_REQUIRED"
            sunat_act_res.payload["cross_source_reason"] = None if is_consistent else "ACTIVITY_SOURCE_MISMATCH"

            # Also classify Decolecta activity independently for UI
            dec_ciiu_res = self.ciiu.validate(db, [{"descripcion_sunat": decolecta_activity, "tipo": "DECOLECTA"}], False, "")
            if dec_ciiu_res.payload and dec_ciiu_res.payload.get("results"):
                sunat_act_res.payload["decolecta_ciiu_result"] = dec_ciiu_res.payload["results"][0]

        # Create ValidationRequests
        for name, res in [("SUNAT", sunat_res), ("MIGO_ACTIVITIES", sunat_act_res), ("RNP", rnp_res), ("FUP", fup_res), ("CIIU", ciiu_res)]:
            req = ValidationRequest(
                supplier_id=supplier_id,
                case_id=case_id,
                source=name,
                status=res.status,
                requested_by=user_id,
                response_payload=res.payload,
                response_schema_version=res.schema_version,
                response_hash=res.hash,
                completed_at=func.now()
            )
            db.add(req)

        # Consolidate Supplier Profile Status
        statuses = [sunat_res.status, rnp_res.status, fup_res.status, ciiu_res.status]
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
