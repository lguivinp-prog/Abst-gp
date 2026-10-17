from sqlalchemy.orm import Session
from app.models.v6.supplier_offer import SupplierOffer
from app.models.v6.case_requirement_matrix import CaseRequirementMatrix
from app.models.v6.offer_evidence import OfferEvidence
from app.models.v6.offer_requirement_evidence import OfferRequirementEvidence
from app.models.v6.offer_evaluation import OfferEvaluation
from app.models.domain import AuditLog, CaseFile
from app.services.v6.engines.improvement_engine import DeterministicImprovementEngine
from typing import List, Optional
import json

class OfferEvaluationService:
    def __init__(self, engine: DeterministicImprovementEngine = None):
        self.engine = engine or DeterministicImprovementEngine()

    def evaluate_offer(self, db: Session, supplier_offer_id: int, user_id: int, tenant_id: str) -> list:
        offer = db.query(SupplierOffer).filter_by(id=supplier_offer_id).first()
        if not offer:
            return []

        case = db.query(CaseFile).filter_by(id=offer.case_id).first()
        if case and case.status in ["APPROVED", "COMPLETED"]:
            # Terminal cases are immutable
            return db.query(OfferEvaluation).filter_by(supplier_offer_id=offer.id).all()

        requirements = db.query(CaseRequirementMatrix).filter_by(case_id=offer.case_id).all()
        evaluations = []
        has_conflicts = False

        try:
            for req in requirements:
                eval_entry = self._evaluate_single_requirement_in_tx(db, offer, req)
                if eval_entry.status == "CONFLICT":
                    has_conflicts = True
                evaluations.append(eval_entry)

            if has_conflicts:
                offer.evaluation_status = "HAS_CONFLICTS"
            else:
                offer.evaluation_status = "UNDER_REVIEW"

            audit = AuditLog(
                user_id=user_id,
                tenant_id=tenant_id,
                action="EVALUATE_OFFER",
                entity_type="SupplierOffer",
                entity_id=str(offer.id),
                details=json.dumps({"has_conflicts": has_conflicts, "eval_count": len(evaluations)}),
                status="SUCCESS"
            )
            db.add(audit)
            db.commit()
            return evaluations
        except Exception as e:
            db.rollback()
            raise e

    def _evaluate_single_requirement_in_tx(self, db: Session, offer: SupplierOffer, req: CaseRequirementMatrix) -> OfferEvaluation:
        # P12: Solo evidencias vinculadas explícitamente a este requisito y oferta
        req_evs = db.query(OfferRequirementEvidence).filter_by(
            supplier_offer_id=offer.id,
            requirement_id=req.id
        ).all()

        # CONTROL 1 & 4: Fail-closed: verificar que cada evidencia vinculada conserva una fuente documental real y existente
        from app.models.domain import UploadedDocument
        valid_evs = []
        for ev in req_evs:
            if not ev.offer_evidence_id:
                continue
            oe = db.query(OfferEvidence).filter_by(id=ev.offer_evidence_id, supplier_offer_id=offer.id).first()
            if not oe:
                # La fuente OfferEvidence fue eliminada o no pertenece a la oferta: fail-closed
                continue
            if not ev.document_id:
                # Sin documento real registrado: no puede producir acreditación
                continue
            doc = db.query(UploadedDocument).filter_by(id=ev.document_id, case_id=offer.case_id).first()
            if not doc:
                # El documento fuente fue eliminado o no pertenece al expediente: fail-closed
                continue
            if oe.document_id is not None and oe.document_id != ev.document_id:
                # Discrepancia entre el documento de la evidencia y el documento vinculado: fail-closed
                continue
            if not ev.fragment or not ev.fragment.strip():
                continue
            valid_evs.append(ev)

        status = "MISSING_DATA"
        explanation = "No se encontro evidencia documental vinculada para este requisito"
        confidence = 0.0

        if not valid_evs:
            status = "MISSING_DATA"
            explanation = "No se encontro evidencia documental verificable para este requisito"
            confidence = 0.0
        elif self.engine.detect_conflict(valid_evs):
            status = "CONFLICT"
            explanation = "Conflicto documental detectado entre las evidencias vinculadas"
            confidence = 0.85
        elif any(ev.verification_status == "REJECTED" for ev in valid_evs):
            status = "FAILED"
            explanation = "Incumplimiento acreditado por evidencia documental rechazada"
            confidence = 1.0
        elif any(ev.verification_status in ["PENDING", "OBSERVED"] for ev in valid_evs) or not any(ev.verification_status == "VERIFIED" for ev in valid_evs):
            # Evidencia vinculada sin revisión suficiente: pendiente de revisión
            status = "REQUIERE_REVISION"
            explanation = "Evidencia vinculada pendiente de verificacion humana suficiente"
            confidence = 0.5
        else:
            # Todas las evidencias vinculadas están validadas y sin rechazo ni conflicto
            verified_evs = [ev for ev in valid_evs if ev.verification_status == "VERIFIED"]
            # P12: Separar verificación documental y cumplimiento técnico
            # Una evidencia verificada NO implica automáticamente cumplimiento (PASSED/IMPROVEMENT)
            contrast_res = self.engine.contrast_technical_compliance(
                req_desc=req.description,
                req_value=req.value,
                fragments=[ev.fragment for ev in verified_evs if ev.fragment]
            )
            status = contrast_res["status"]
            explanation = contrast_res["explanation"]
            confidence = contrast_res["confidence"]

        # CONTROL 2: In-place atomic and concurrent-safe upsert with PostgreSQL ON CONFLICT DO UPDATE
        bind = db.get_bind()
        if bind and bind.dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            from sqlalchemy.sql import func
            stmt = pg_insert(OfferEvaluation).values(
                supplier_offer_id=offer.id,
                requirement_id=req.id,
                status=status,
                explanation=explanation,
                evaluation_confidence=confidence,
                created_at=func.now()
            ).on_conflict_do_update(
                constraint="uq_offer_evaluations_offer_req",
                set_={
                    "status": status,
                    "explanation": explanation,
                    "evaluation_confidence": confidence,
                }
            ).returning(OfferEvaluation.id)
            res = db.execute(stmt)
            eval_id = res.scalar_one()
            eval_entry = db.query(OfferEvaluation).filter_by(id=eval_id).first()
        else:
            # Fallback for SQLite in pure unit test environments
            eval_entry = db.query(OfferEvaluation).filter_by(
                supplier_offer_id=offer.id,
                requirement_id=req.id
            ).first()
            if eval_entry:
                eval_entry.status = status
                eval_entry.explanation = explanation
                eval_entry.evaluation_confidence = confidence
            else:
                eval_entry = OfferEvaluation(
                    supplier_offer_id=offer.id,
                    requirement_id=req.id,
                    status=status,
                    explanation=explanation,
                    evaluation_confidence=confidence
                )
                db.add(eval_entry)
                db.flush()

        return eval_entry

    def reevaluate_requirement(self, db: Session, supplier_offer_id: int, requirement_id: int, user_id: int, tenant_id: str, auto_commit: bool = True) -> Optional[OfferEvaluation]:
        offer = db.query(SupplierOffer).filter_by(id=supplier_offer_id).first()
        if not offer:
            return None

        case = db.query(CaseFile).filter_by(id=offer.case_id).first()
        if case and case.status in ["APPROVED", "COMPLETED"]:
            return db.query(OfferEvaluation).filter_by(supplier_offer_id=offer.id, requirement_id=requirement_id).first()

        req = db.query(CaseRequirementMatrix).filter_by(id=requirement_id).first()
        if not req:
            return None

        try:
            eval_entry = self._evaluate_single_requirement_in_tx(db, offer, req)

            # Check offer overall conflict status
            conflicts = db.query(OfferEvaluation).filter_by(supplier_offer_id=offer.id, status="CONFLICT").count()
            if conflicts > 0:
                offer.evaluation_status = "HAS_CONFLICTS"
            elif offer.evaluation_status == "HAS_CONFLICTS":
                offer.evaluation_status = "UNDER_REVIEW"

            if auto_commit:
                audit = AuditLog(
                    user_id=user_id,
                    tenant_id=tenant_id,
                    action="REEVALUATE_REQUIREMENT",
                    entity_type="OfferEvaluation",
                    entity_id=str(eval_entry.id) if eval_entry.id else str(requirement_id),
                    details=json.dumps({"supplier_offer_id": supplier_offer_id, "requirement_id": requirement_id, "new_status": eval_entry.status}),
                    status="SUCCESS"
                )
                db.add(audit)
                db.commit()
                db.refresh(eval_entry)
            else:
                db.flush()

            return eval_entry
        except Exception as e:
            if auto_commit:
                db.rollback()
            raise e

    def update_evaluation(self, db: Session, eval_id: int, new_status: str, explanation: str, user_id: int, tenant_id: str) -> OfferEvaluation:
        eval_entry = db.query(OfferEvaluation).filter_by(id=eval_id).first()
        if not eval_entry:
            return None

        clean_exp = (explanation or "").strip()
        if not clean_exp:
            raise ValueError("Explanation/justification is mandatory when setting human evaluation decision.")

        # CONTROL 3: Validar que no sea posible asignar manualmente PASSED o IMPROVEMENT
        # sin asociación documental específica válida y verificada (VERIFIED) con documento fuente real
        if new_status in ["PASSED", "IMPROVEMENT", "CUMPLE", "CUMPLE_Y_MEJORA"]:
            from app.models.domain import UploadedDocument
            offer = db.query(SupplierOffer).filter_by(id=eval_entry.supplier_offer_id).first()
            req = db.query(CaseRequirementMatrix).filter_by(id=eval_entry.requirement_id).first()
            req_evs = db.query(OfferRequirementEvidence).filter_by(
                supplier_offer_id=eval_entry.supplier_offer_id,
                requirement_id=eval_entry.requirement_id
            ).all()

            valid_verified = []
            for ev in req_evs:
                if ev.verification_status == "VERIFIED" and ev.offer_evidence_id and ev.document_id:
                    oe = db.query(OfferEvidence).filter_by(id=ev.offer_evidence_id, supplier_offer_id=eval_entry.supplier_offer_id).first()
                    if oe:
                        doc = db.query(UploadedDocument).filter_by(id=ev.document_id, case_id=offer.case_id if offer else None).first()
                        if doc and (oe.document_id is None or oe.document_id == ev.document_id) and ev.fragment and ev.fragment.strip():
                            valid_verified.append(ev)

            if not valid_verified:
                raise ValueError("Cannot assign positive compliance (PASSED/IMPROVEMENT) without specific verified documentary evidence.")
            if any(ev.verification_status == "REJECTED" for ev in req_evs):
                raise ValueError("Cannot assign positive compliance when requirement has REJECTED evidence.")
            if self.engine.detect_conflict(req_evs):
                raise ValueError("Cannot assign positive compliance when requirement has unresolved CONFLICT.")

            # No permitir que el usuario ignore evidencias contradictorias que demuestran incumplimiento técnico
            if req:
                contrast_res = self.engine.contrast_technical_compliance(
                    req_desc=req.description,
                    req_value=req.value,
                    fragments=[ev.fragment for ev in valid_verified if ev.fragment]
                )
                if contrast_res["status"] == "FAILED":
                    raise ValueError(f"Cannot assign positive compliance when documentary evidence demonstrates non-compliance: {contrast_res['explanation']}")

        from datetime import datetime, timezone
        old_status = eval_entry.status
        eval_entry.status = new_status
        eval_entry.explanation = clean_exp
        eval_entry.validated_by = user_id
        eval_entry.validated_at = datetime.now(timezone.utc)

        audit = AuditLog(
            user_id=user_id,
            tenant_id=tenant_id,
            action="UPDATE_EVALUATION",
            entity_type="OfferEvaluation",
            entity_id=str(eval_entry.id),
            details=json.dumps({
                "old_status": old_status,
                "new_status": new_status,
                "reason": clean_exp,
                "validated_by": user_id
            }),
            status="SUCCESS"
        )
        db.add(audit)

        db.flush()

        # Check if parent offer can be unblocked
        offer = db.query(SupplierOffer).filter_by(id=eval_entry.supplier_offer_id).first()
        still_conflicts = db.query(OfferEvaluation).filter_by(supplier_offer_id=offer.id, status="CONFLICT").count()
        if still_conflicts == 0 and offer.evaluation_status == "HAS_CONFLICTS":
            offer.evaluation_status = "UNDER_REVIEW"

        db.commit()
        db.refresh(eval_entry)
        return eval_entry
