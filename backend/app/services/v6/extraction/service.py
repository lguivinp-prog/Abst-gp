from typing import List
from sqlalchemy.orm import Session
from app.models.v6.case_requirement_matrix import CaseRequirementMatrix
from app.models.v6.requirement_evidence import RequirementEvidence
from app.models.domain import AuditLog
from .provider import RequirementExtractionProvider
from .deterministic_extractor import DeterministicRequirementExtractor
import json

class RequirementExtractionService:
    def __init__(self, extractor: RequirementExtractionProvider = None):
        self.extractor = extractor or DeterministicRequirementExtractor()

    def process_text_and_propose(self, db: Session, case_id: int, user_id: int, tenant_id: str, text: str, document_name: str) -> List[CaseRequirementMatrix]:
        candidates = self.extractor.extract(text=text, source_document=document_name)
        
        created_matrices = []
        for candidate in candidates:
            # Create Matrix Entry
            req = CaseRequirementMatrix(
                case_id=case_id,
                requirement_type=candidate.requirement_type,
                description=candidate.description,
                value=candidate.value,
                mandatory=candidate.mandatory,
                status="PENDING_REVIEW" # Rule: NO automagic approvals
            )
            db.add(req)
            db.flush()
            
            # Create Evidence
            evidence = RequirementEvidence(
                requirement_id=req.id,
                source_document=candidate.source_document,
                source_page=candidate.source_page,
                source_fragment=candidate.source_fragment,
                confidence=candidate.confidence
            )
            db.add(evidence)
            
            # Create Audit Log
            audit = AuditLog(
                user_id=user_id,
                tenant_id=tenant_id,
                action="PROPOSE_REQUIREMENT",
                entity_type="CaseRequirementMatrix",
                entity_id=str(req.id),
                details=json.dumps({
                    "old_value": None,
                    "new_value": req.status,
                    "reason": "Extraction Engine Proposal",
                    "timestamp": None # DB handles this
                }),
                status="SUCCESS"
            )
            db.add(audit)
            created_matrices.append(req)
            
        db.commit()
        return created_matrices
