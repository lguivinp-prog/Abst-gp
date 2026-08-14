from sqlalchemy.orm import Session
from app.models.v6.case_requirement_matrix import CaseRequirementMatrix
from app.models.domain import AuditLog
from datetime import datetime, timezone

class RequirementMatrixService:
    @staticmethod
    def create_requirement(db: Session, case_id: int, user_id: int, tenant_id: str, data: dict) -> CaseRequirementMatrix:
        req = CaseRequirementMatrix(
            case_id=case_id,
            requirement_type=data.get("requirement_type", "TECHNICAL"),
            description=data["description"],
            value=data.get("value"),
            mandatory=data.get("mandatory", True)
        )
        db.add(req)
        db.flush() # Para obtener ID
        
        audit = AuditLog(
            user_id=user_id,
            tenant_id=tenant_id,
            action="CREATE_REQUIREMENT",
            entity_type="CaseRequirementMatrix",
            entity_id=str(req.id),
            details=f"Created requirement {req.id} for case {case_id}",
            status="SUCCESS"
        )
        db.add(audit)
        db.commit()
        db.refresh(req)
        return req

    @staticmethod
    def get_by_case(db: Session, case_id: int) -> list:
        return db.query(CaseRequirementMatrix).filter(CaseRequirementMatrix.case_id == case_id).all()
