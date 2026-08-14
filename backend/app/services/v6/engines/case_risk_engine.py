from sqlalchemy.orm import Session
from app.models.domain import AuditLog
from app.models.v6.supplier_profile import SupplierProfile
from typing import Tuple, List, Dict, Any

class CaseRiskEngine:
    def calculate_risk(self, db: Session, case_id: int) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Deterministically calculates the risk level (LOW, MEDIUM, HIGH) and returns the reasons.
        """
        reasons = []
        risk_level = "LOW"
        
        # 1. Check AuditLogs for Exceptions or Accuracy Gate Failures
        audits = db.query(AuditLog).filter_by(entity_type="CaseFile", entity_id=str(case_id)).all()
        for audit in audits:
            if audit.action == "SUPERVISOR_EXCEPTION_SELECT":
                reasons.append({"type": "SUPERVISOR_EXCEPTION", "source": "AuditLog", "reference_id": audit.id})
            elif audit.action == "ACCURACY_FAILED":
                reasons.append({"type": "ACCURACY_GATE_FAILURE", "source": "ContractAccuracyGate", "reference_id": audit.id})
                
        # 2. Check SupplierProfiles in this case (Mocking relationship, assuming we can find profiles by case offers)
        # For architecture definition, we just do a mock query representing the logic.
        from app.models.v6.supplier_offer import SupplierOffer
        offers = db.query(SupplierOffer).filter_by(case_id=case_id).all()
        for offer in offers:
            profile = db.query(SupplierProfile).filter_by(supplier_id=offer.supplier_id).first()
            if profile:
                if profile.validation_status == "BLOCKED":
                    reasons.append({"type": "BLOCKED_VALIDATION", "source": "SupplierProfile", "reference_id": profile.id})
                elif profile.validation_status == "WARNING":
                    reasons.append({"type": "WARNING_VALIDATION", "source": "SupplierProfile", "reference_id": profile.id})
                elif profile.validation_status in ["PENDING", "NOT_STARTED", "PARTIAL"]:
                    reasons.append({"type": "INCOMPLETE_EVIDENCE", "source": "SupplierProfile", "reference_id": profile.id})
        
        # Check for mock CONFLICT state in CaseWorkflow (Assuming it's stored in a workflow table or audit)
        for audit in audits:
            if audit.action == "CONFLICT_DETECTED":
                reasons.append({"type": "CONFLICT", "source": "OfferEvaluation", "reference_id": audit.id})
            if audit.action == "MISSING_DATA_DETECTED":
                reasons.append({"type": "MISSING_DATA", "source": "ExtractionEngine", "reference_id": audit.id})

        # Calculate final risk
        high_triggers = ["SUPERVISOR_EXCEPTION", "ACCURACY_GATE_FAILURE", "BLOCKED_VALIDATION", "CONFLICT"]
        medium_triggers = ["MISSING_DATA", "INCOMPLETE_EVIDENCE", "WARNING_VALIDATION"]
        
        for reason in reasons:
            if reason["type"] in high_triggers:
                risk_level = "HIGH"
                break
            elif reason["type"] in medium_triggers:
                risk_level = "MEDIUM"
                
        return risk_level, reasons
