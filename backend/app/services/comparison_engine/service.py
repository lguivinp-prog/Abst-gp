import logging
from uuid import UUID
from typing import List, Tuple, Optional
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.models.domain import (
    ComparisonRun, ComparisonRunStatus, RequirementItem,
    ParsedSection, ComparisonResult, EvaluationMethod,
    UploadedDocument
)
from app.services.comparison_engine.exceptions import (
    ComparisonDomainError, ComparisonRunNotFound,
    ComparisonInvalidState, ComparisonRunNotClaimed,
    ComparisonProcessingError
)
from app.services.comparison_engine.matcher import ComparisonMatcher
from app.services.comparison_engine.scoring import ComparisonScorer

logger = logging.getLogger(__name__)

@dataclass
class SnapshotRequirement:
    requirement_item_id: int
    content_text: str
    item_type: str
    requirement_page: int

@dataclass
class SnapshotSection:
    quotation_section_id: int
    cleaned_text: str
    page: int

class ComparisonEngineService:
    def __init__(self, db: Session):
        self.db = db

    def execute_run(self, run_id: UUID) -> ComparisonRun:
        claimed = False
        try:
            self._claim_run(run_id)
            claimed = True
            
            reqs_snapshot, sections_snapshot = self._load_data_snapshot(run_id)
            if not reqs_snapshot:
                raise ComparisonDomainError(f'Cero requisitos aprobados para evaluar en run {run_id}.')
            
            results_to_insert = self._process_items(run_id, reqs_snapshot, sections_snapshot)
            run = self._commit_results(run_id, results_to_insert)
            return run
            
        except ComparisonRunNotClaimed:
            logger.warning(f"ComparisonRun {run_id} no pudo ser reclamado.")
            raise
        except Exception:
            logger.error(f"Error procesando ComparisonRun {run_id}", exc_info=True)
            if claimed:
                try:
                    self._mark_failed(run_id)
                except Exception as mark_e:
                    logger.error(f"Fallo al marcar failed: {mark_e}")
            raise

    def _claim_run(self, run_id: UUID) -> None:
        stmt = sa.text("""
            UPDATE comparison_runs
            SET status = 'PROCESSING'
            WHERE id = :run_id AND status = 'CREATED'
            RETURNING id
        """)
        claimed_id = self.db.execute(stmt, {"run_id": run_id}).scalar_one_or_none()
        self.db.commit()
        
        if not claimed_id:
            run_status_stmt = sa.text("SELECT status FROM comparison_runs WHERE id = :run_id")
            status_row = self.db.execute(run_status_stmt, {"run_id": run_id}).fetchone()
            
            self.db.rollback()
            if not status_row:
                raise ComparisonRunNotFound(f'ComparisonRun {run_id} no existe.')
            status = status_row[0]
            if status == 'PROCESSING':
                raise ComparisonRunNotClaimed(f'ComparisonRun {run_id} no pudo ser reclamado. Estado actual: {status}')
            else:
                raise ComparisonInvalidState(f'ComparisonRun {run_id} no puede ser reclamado. Estado actual: {status}')

    def _load_data_snapshot(self, run_id: UUID) -> Tuple[List[SnapshotRequirement], List[SnapshotSection]]:
        run = self.db.query(ComparisonRun).filter(ComparisonRun.id == run_id).first()
        case_id = run.case_id
        req_doc_id = run.requirement_doc_id
        quot_doc_id = run.quotation_doc_id
        
        req_doc = self.db.query(UploadedDocument).filter(UploadedDocument.id == req_doc_id).first()
        quot_doc = self.db.query(UploadedDocument).filter(UploadedDocument.id == quot_doc_id).first()
        
        if not req_doc or req_doc.case_id != case_id or req_doc.document_type != 'requirement':
            raise ComparisonDomainError("Requirement document no pertenece al caso del run o no es requirement.")
        if not quot_doc or quot_doc.case_id != case_id or quot_doc.document_type != 'quotation':
            raise ComparisonDomainError("Quotation document no pertenece al caso del run o no es quotation.")
        
        req_stmt = sa.select(
            RequirementItem.id,
            RequirementItem.content_text,
            RequirementItem.item_type,
            ParsedSection.extraction_metadata
        ).select_from(RequirementItem).join(
            ParsedSection, RequirementItem.parsed_section_id == ParsedSection.id
        ).where(
            ParsedSection.document_id == req_doc_id,
            ParsedSection.case_id == case_id,
            RequirementItem.is_approved == True
        )
        req_rows = self.db.execute(req_stmt).all()

        quot_stmt = sa.select(
            ParsedSection.id,
            ParsedSection.cleaned_text,
            ParsedSection.extraction_metadata
        ).where(
            ParsedSection.document_id == quot_doc_id,
            ParsedSection.case_id == case_id
        )
        quot_rows = self.db.execute(quot_stmt).all()
        
        reqs_snapshot = [
            SnapshotRequirement(
                requirement_item_id=row[0],
                content_text=row[1],
                item_type=row[2],
                requirement_page=(row[3].get('page', 1) if row[3] else 1)
            )
            for row in req_rows
        ]
        
        sections_snapshot = [
            SnapshotSection(
                quotation_section_id=row[0],
                cleaned_text=row[1] or "",
                page=(row[2].get('page', 1) if row[2] else 1)
            )
            for row in quot_rows
        ]
        
        self.db.commit()
        return reqs_snapshot, sections_snapshot

    def _process_items(
        self, 
        run_id: UUID, 
        reqs: List[SnapshotRequirement], 
        sections: List[SnapshotSection]
    ) -> List[ComparisonResult]:
        
        matcher_sections = [
            {'id': s.quotation_section_id, 'text': s.cleaned_text, 'page': s.page}
            for s in sections
        ]
        matcher = ComparisonMatcher(quotation_sections=matcher_sections)
        scorer = ComparisonScorer()
        
        results_orm = []
        for req in reqs:
            candidates = matcher.find_candidates(req.content_text)
            decision = scorer.evaluate(req.content_text, candidates)
            
            result = ComparisonResult(
                run_id=run_id,
                requirement_item_id=req.requirement_item_id,
                status=decision.status,
                confidence_score=decision.confidence_score,
                reasoning=decision.reasoning,
                requirement_page=req.requirement_page
            )
            
            if decision.selected_candidate:
                result.evaluation_method = decision.evaluation_method
                result.quotation_section_id = decision.selected_candidate.quotation_section_id
                result.quotation_page = decision.selected_candidate.page
                result.evidence_text = decision.selected_candidate.text
            else:
                result.evaluation_method = EvaluationMethod.NO_MATCH
                result.quotation_section_id = None
                result.quotation_page = None
                result.evidence_text = None
                
            results_orm.append(result)
            
        return results_orm

    def _commit_results(self, run_id: UUID, results: List[ComparisonResult]) -> ComparisonRun:
        run = self.db.query(ComparisonRun).filter(ComparisonRun.id == run_id).with_for_update().first()
        
        if not run:
            raise ComparisonRunNotFound(f"ComparisonRun {run_id} no encontrado en commit final.")
            
        if run.status != ComparisonRunStatus.PROCESSING:
            raise ComparisonInvalidState(f"El run {run_id} ya no esta en PROCESSING (actual: {run.status}).")
            
        existing_count = self.db.query(ComparisonResult).filter(ComparisonResult.run_id == run_id).count()
        if existing_count > 0:
            raise ComparisonInvalidState(f"El run {run_id} ya tiene resultados generados.")
            
        self.db.add_all(results)
        run.status = ComparisonRunStatus.COMPLETED
        self.db.commit()
        self.db.refresh(run)
        return run

    def _mark_failed(self, run_id: UUID) -> None:
        self.db.rollback()
        try:
            run = self.db.query(ComparisonRun).filter(ComparisonRun.id == run_id).with_for_update().first()
            if run and run.status == ComparisonRunStatus.PROCESSING:
                run.status = ComparisonRunStatus.FAILED
                self.db.commit()
            else:
                self.db.rollback()
        except Exception as fallback_e:
            self.db.rollback()
            logger.exception(f"Error critico al marcar FAILED el run {run_id}: {fallback_e}")