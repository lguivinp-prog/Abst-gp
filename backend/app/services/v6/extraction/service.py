from typing import List
from sqlalchemy.orm import Session
from app.models.v6.case_requirement_matrix import CaseRequirementMatrix
from app.models.v6.requirement_evidence import RequirementEvidence
from app.models.domain import AuditLog
from .provider import RequirementExtractionProvider
from .deterministic_extractor import DeterministicRequirementExtractor
from app.services.v6.extraction.contract_extractor import extract_requirements_from_text, is_template_instruction
import json

class RequirementExtractionService:
    def __init__(self, extractor: RequirementExtractionProvider = None):
        self.extractor = extractor or DeterministicRequirementExtractor()

    def process_text_and_propose(self, db: Session, case_id: int, user_id: int, tenant_id: str, text: str, document_name: str, document_id: int = None, skip_requirements: bool = False) -> List[CaseRequirementMatrix]:
        from app.models.v6.case_procurement_item import CaseProcurementItem, CaseProcurementItemSpecification
        # Idempotency: remove previously automatically extracted items for this document
        processed_item_numbers = set()
        seen_descriptions = set()
        preserved_contractual_keys = set()

        if document_id:
            existing_items = db.query(CaseProcurementItem).filter_by(case_id=case_id, source_document_id=document_id).all()
            for existing in existing_items:
                if getattr(existing, 'is_manual_edit', False) or existing.status in ["VALIDATED", "MODIFIED_BY_USER"]:
                    if existing.item_number is not None:
                        processed_item_numbers.add(existing.item_number)
                    continue
                db.delete(existing)

            # Idempotency for Requirements (All types)
            if not skip_requirements:
                existing_reqs = db.query(CaseRequirementMatrix).filter_by(case_id=case_id, source_document_id=document_id).all()
                for existing in existing_reqs:
                    if getattr(existing, 'is_manual_edit', False) or existing.status in ["VALIDATED", "MODIFIED_BY_USER", "OBSERVED", "REJECTED"]:
                        normalized_desc = " ".join((existing.description or "").split()).casefold()
                        seen_descriptions.add(normalized_desc)
                        if existing.requirement_type == "CONTRACTUAL" and existing.key:
                            preserved_contractual_keys.add(existing.key)
                        continue
                    db.delete(existing)

            db.flush()

        result = self.extractor.extract(text=text, source_document=document_name)

        created_matrices = []
        if not skip_requirements:
            for candidate in result.requirements:
                if is_template_instruction(candidate.description):
                    continue

                normalized_desc = " ".join(candidate.description.split()).casefold()
                if normalized_desc in seen_descriptions:
                    continue

                # Deduplicate if TECHNICAL is actually a contractual condition
                if candidate.requirement_type == "TECHNICAL":
                    temp_contract = extract_requirements_from_text(candidate.description)
                    if temp_contract.get("requirements"):
                        continue

                seen_descriptions.add(normalized_desc)
                # OCR QUALITY GATE
                # Campos crÃ­ticos si la confianza < 0.85 -> REVIEW_REQUIRED
                threshold = 0.85
                req_status = "REVIEW_REQUIRED" if candidate.confidence < threshold else "PENDING_REVIEW"

                # Create Matrix Entry
                req = CaseRequirementMatrix(
                    case_id=case_id,
                    source_document_id=document_id,
                    requirement_type=candidate.requirement_type,
                    description=candidate.description,
                    value=candidate.value,
                    mandatory=candidate.mandatory,
                    status=req_status
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

            # Contractual Requirements
            contract_res = extract_requirements_from_text(text, source_document=document_name)
            for c_req in contract_res.get("requirements", []):
                if c_req["key"] in preserved_contractual_keys:
                    continue
                req_status = "REVIEW_REQUIRED" if c_req["confidence"] < 0.85 else "PENDING_REVIEW"
                req = CaseRequirementMatrix(
                    case_id=case_id,
                    source_document_id=document_id,
                    requirement_type="CONTRACTUAL",
                    key=c_req["key"],
                    description=c_req["description"],
                    value=str(c_req["numeric_value"]) if c_req["numeric_value"] is not None else None,
                    numeric_value=c_req["numeric_value"],
                    unit=c_req["unit"],
                    comparator=c_req["comparator"],
                    mandatory=True,
                    status=req_status
                )
                db.add(req)
                db.flush()

                evidence = RequirementEvidence(
                    requirement_id=req.id,
                    source_document=c_req["source_document_id"],
                    source_page=c_req["source_page"],
                    source_fragment=c_req["source_quote"],
                    confidence=c_req["confidence"]
                )
                db.add(evidence)
                created_matrices.append(req)

        # We map items by item_number to avoid duplicates when processing 5.2 (if the extractor happens to merge them)
        # processed_item_numbers is already initialized and populated with validated items above
        for item in result.items:
            # Skip if we already added this item number (to prevent duplicates if paginated)
            if item.item_number in processed_item_numbers:
                continue
            processed_item_numbers.add(item.item_number)

            item_status = "REVIEW_REQUIRED" if item.needs_review else "VALIDATED"
            proc_item = CaseProcurementItem(
                case_id=case_id,
                item_number=item.item_number,
                description=item.description,
                quantity=item.quantity,
                unit=item.unit,
                source_document_id=document_id,
                source_page=item.source_page,
                status=item_status,
                confidence=item.confidence
            )
            db.add(proc_item)
            db.flush()

            for spec in item.specifications:
                proc_item_spec = CaseProcurementItemSpecification(
                    procurement_item_id=proc_item.id,
                    name=spec.name,
                    normalized_name=spec.normalized_name,
                    value=spec.value,
                    mandatory=spec.mandatory,
                    source_document_id=document_id,
                    source_page=spec.source_page,
                    confidence=spec.confidence
                )
                db.add(proc_item_spec)

        db.commit()
        return created_matrices
