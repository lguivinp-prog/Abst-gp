from typing import Dict, Any, List, Optional
from decimal import Decimal
from sqlalchemy.orm import Session
from app.models.domain import CaseFile, UploadedDocument, AuditLog, User
from app.models.v6.case_workflow import CaseWorkflow
from app.models.v6.supplier_selection import SupplierSelectionFinal, SupplierSelectionAttempt
from app.models.v6.supplier_offer import SupplierOffer
from app.models.v6.supplier_profile import SupplierProfile
from app.models.v6.case_requirement_matrix import CaseRequirementMatrix
from app.models.v6.offer_evaluation import OfferEvaluation
from app.models.v6.offer_requirement_evidence import OfferRequirementEvidence
from app.models.v6.offer_evidence import OfferEvidence
from app.services.v6.evaluation.vfm_service import ValueForMoneyService


class TechnicalReportAccuracyGate:
    """
    Gate de exactitud documental para generación de informes técnicos P13.
    Verifica de manera fail-closed:
    1. Expediente y Workflow en estado APPROVED pertenecientes al tenant.
    2. Cadena de verdad íntegra: CaseFile -> CaseWorkflow -> SupplierSelectionFinal -> SupplierSelectionAttempt -> SupplierOffer.
    3. Importe positivo válido y código de moneda ISO auténtico.
    4. Perfil del proveedor ganador con estado VERIFIED o excepción documentada de supervisor.
    5. Existencia obligatoria de requisitos en la matriz de requerimientos.
    6. Evaluaciones positivas válidas para todos los requisitos obligatorios.
    7. Trazabilidad documental P12 estricta sin omisiones ni evidencias contradictorias/huérfanas:
       case -> offer -> requirement -> OfferRequirementEvidence(VERIFIED) -> OfferEvidence -> UploadedDocument
       con IDs coherentes, tenant idéntico, fragmento textual original no vacío, página válida y verificador.
    8. Elegibilidad real comprobada según el motor Value for Money (VfM).
    """

    POSITIVE_EVAL_STATUSES = {"PASSED", "IMPROVEMENT", "CUMPLE", "CUMPLE_Y_MEJORA"}
    VALID_ISO_CURRENCIES = {"PEN", "USD", "EUR"}

    @classmethod
    def validate_for_p13(cls, db: Session, case_id: int, tenant_id: str) -> Dict[str, Any]:
        errors: List[str] = []

        # 1. Caso y Workflow
        case = db.query(CaseFile).filter_by(id=case_id).first()
        if not case:
            return {"status": "FAIL", "errors": [f"Expediente {case_id} no encontrado."]}

        if case.tenant_id != tenant_id:
            return {"status": "FAIL", "errors": ["Acceso denegado: el expediente no pertenece al tenant."]}

        if case.status != "APPROVED":
            errors.append(f"El expediente no se encuentra en estado APPROVED (actual: {case.status}).")

        workflow = db.query(CaseWorkflow).filter_by(case_id=case_id).first()
        if not workflow or workflow.status != "APPROVED":
            curr_wf_status = workflow.status if workflow else "NO_EXISTE"
            errors.append(f"El flujo de trabajo no se encuentra en estado APPROVED (actual: {curr_wf_status}).")

        # 2. Selección Final y Cadena de Selección
        selection_final = db.query(SupplierSelectionFinal).filter_by(case_id=case_id).first()
        if not selection_final:
            errors.append("No existe registro de selección final (SupplierSelectionFinal) para este expediente.")
            return {"status": "FAIL", "errors": errors}

        attempt = db.query(SupplierSelectionAttempt).filter_by(id=selection_final.attempt_id, case_id=case_id).first()
        if not attempt:
            errors.append(f"El intento de selección {selection_final.attempt_id} no fue encontrado o no pertenece al expediente {case_id}.")
            return {"status": "FAIL", "errors": errors}

        winning_offer = db.query(SupplierOffer).filter_by(id=attempt.supplier_offer_id, case_id=case_id).first()
        if not winning_offer:
            errors.append(f"La oferta ganadora {attempt.supplier_offer_id} no pertenece al expediente {case_id}.")
            return {"status": "FAIL", "errors": errors}

        # 3. Importe y Moneda de la Oferta Ganadora
        raw_price = winning_offer.total_amount if winning_offer.total_amount is not None else winning_offer.price
        if raw_price is None or Decimal(str(raw_price)) <= 0:
            errors.append("La oferta ganadora carece de un importe contractual válido positivo.")

        curr = (winning_offer.currency or "").strip().upper()
        if not curr or curr not in cls.VALID_ISO_CURRENCIES:
            errors.append(f"La oferta ganadora presenta una moneda no admitida o inválida ('{winning_offer.currency}').")

        # 4. Perfil del Proveedor Ganador
        profile = db.query(SupplierProfile).filter_by(supplier_id=winning_offer.supplier_id).first()
        if not profile:
            errors.append("No se encontró el perfil del proveedor seleccionado.")
        else:
            # R3-02: Proveedores sancionados o bloqueados están estrictamente prohibidos
            if profile.validation_status in ["SANCTIONED", "BLOCKED"]:
                errors.append(
                    f"El proveedor seleccionado ({winning_offer.supplier_id}) se encuentra en estado {profile.validation_status}; adjudicación estrictamente prohibida por política de integridad."
                )
            elif profile.validation_status != "VERIFIED":
                # R3-02: P12 SelectionService registra legítimamente SUPERVISOR_EXCEPTION_SELECT con status WARNING
                # Se admite WARNING o SUCCESS siempre que exista correlación exacta de actor, oferta, tenant y justificación
                exception_log = db.query(AuditLog).filter(
                    AuditLog.tenant_id == tenant_id,
                    AuditLog.entity_type == "SupplierOffer",
                    AuditLog.entity_id == str(winning_offer.id),
                    AuditLog.action == "SUPERVISOR_EXCEPTION_SELECT",
                    AuditLog.status.in_(["WARNING", "SUCCESS"])
                ).order_by(AuditLog.id.desc()).first()
                if not exception_log:
                    errors.append(
                        f"El proveedor seleccionado tiene estado de validación {profile.validation_status} sin excepción autorizada en el tenant."
                    )
                else:
                    actor = db.query(User).filter_by(id=exception_log.user_id, tenant_id=tenant_id).first()
                    if not actor or actor.role not in ["SUPERVISOR", "ADMIN"]:
                        errors.append(
                            "La excepción registrada para el proveedor no fue emitida por un actor con rol SUPERVISOR o ADMIN autorizado."
                        )
                    if not exception_log.details or len(exception_log.details.strip()) < 10:
                        errors.append("La excepción de supervisor carece de justificación/motivación material suficiente.")
                    from datetime import timedelta
                    if (
                        selection_final
                        and exception_log.created_at
                        and selection_final.created_at
                        and exception_log.created_at > (selection_final.created_at + timedelta(seconds=60))
                    ):
                        errors.append("La excepción de supervisor fue registrada con posterioridad a la adjudicación final, violando la causalidad temporal.")

        # 5. Requerimientos Obligatorios
        mandatory_reqs = db.query(CaseRequirementMatrix).filter_by(case_id=case_id, mandatory=True).order_by(CaseRequirementMatrix.id).all()
        if not mandatory_reqs:
            errors.append("El expediente carece de requisitos obligatorios definidos en la matriz de requerimientos.")

        offer_evals = db.query(OfferEvaluation).filter_by(supplier_offer_id=winning_offer.id).all()
        eval_map = {e.requirement_id: e for e in offer_evals}

        for req in mandatory_reqs:
            if req.id not in eval_map:
                errors.append(f"Requerimiento obligatorio '{req.description or req.id}' no cuenta con evaluación.")
                continue

            ev = eval_map[req.id]
            if ev.status not in cls.POSITIVE_EVAL_STATUSES:
                errors.append(
                    f"Requerimiento obligatorio '{req.description or req.id}' tiene evaluación no aprobatoria ({ev.status})."
                )

        # 6. Trazabilidad de Evidencias Documentales
        traceability_regime = getattr(case, "traceability_regime", "P12_STRICT") or "P12_STRICT"

        if traceability_regime == "P12_STRICT" and mandatory_reqs:
            for req in mandatory_reqs:
                # Consultar todas las asociaciones de evidencia para el requerimiento
                all_req_evidences = db.query(OfferRequirementEvidence).filter_by(
                    case_id=case_id,
                    supplier_offer_id=winning_offer.id,
                    requirement_id=req.id
                ).all()

                if not all_req_evidences:
                    errors.append(
                        f"Requerimiento obligatorio '{req.description or req.id}' carece de evidencia VERIFIED en régimen P12_STRICT."
                    )
                    continue

                # Verificar consistencia: ninguna evidencia asociada puede tener estado negativo o no VERIFIED
                has_verified = False
                for req_evidence in all_req_evidences:
                    if req_evidence.verification_status != "VERIFIED":
                        errors.append(
                            f"Evidencia para '{req.description or req.id}' presenta estado no verificado ({req_evidence.verification_status})."
                        )
                        continue

                    has_verified = True

                    # Verificar integridad de OfferEvidence
                    offer_ev = db.query(OfferEvidence).filter_by(
                        id=req_evidence.offer_evidence_id,
                        supplier_offer_id=winning_offer.id
                    ).first()

                    if not offer_ev:
                        errors.append(
                            f"Evidencia huérfana en requerimiento '{req.description or req.id}': OfferEvidence {req_evidence.offer_evidence_id} no encontrada o pertenece a otra oferta."
                        )
                        continue

                    # Fragmento textual original no vacío
                    frag1 = (req_evidence.fragment or "").strip()
                    frag2 = (offer_ev.fragment or "").strip()
                    if not frag1 and not frag2:
                        errors.append(
                            f"La evidencia para '{req.description or req.id}' tiene fragmento original vacío o en blanco."
                        )
                    elif frag1 and frag2 and frag1 != frag2:
                        errors.append(
                            f"Divergencia de fragmento textual en '{req.description or req.id}': OfferRequirementEvidence y OfferEvidence presentan fragmentos discordantes."
                        )

                    # Número de página válido
                    p1 = req_evidence.page
                    p2 = offer_ev.page
                    if p1 is None and p2 is None:
                        errors.append(
                            f"La evidencia para '{req.description or req.id}' carece de número de página válido."
                        )
                    elif (p1 is not None and p1 < 1) or (p2 is not None and p2 < 1):
                        errors.append(
                            f"La evidencia para '{req.description or req.id}' presenta número de página menor a 1 (p1={p1}, p2={p2})."
                        )
                    elif p1 is not None and p2 is not None and p1 != p2:
                        errors.append(
                            f"Divergencia de número de página en '{req.description or req.id}': OfferRequirementEvidence indica pág {p1} y OfferEvidence indica pág {p2}."
                        )

                    # Procedencia documental auténtica en el expediente
                    d1 = req_evidence.document_id
                    d2 = offer_ev.document_id
                    if not d1 and not d2:
                        errors.append(
                            f"La evidencia para '{req.description or req.id}' no referencia ningún documento fuente."
                        )
                    elif d1 and d2 and d1 != d2:
                        errors.append(
                            f"Inconsistencia crítica de procedencia documental en '{req.description or req.id}': OfferRequirementEvidence referencia doc {d1} y OfferEvidence referencia doc {d2}."
                        )
                    else:
                        doc_id = d1 or d2
                        doc = db.query(UploadedDocument).filter_by(id=doc_id, case_id=case_id).first()
                        if not doc:
                            errors.append(
                                f"La evidencia para '{req.description or req.id}' hace referencia a un documento {doc_id} inexistente o de otro expediente."
                            )
                        else:
                            # R3-04 / R3-08: En régimen P12_STRICT el documento debe existir físicamente en almacenamiento autorizado
                            from app.services.v6.reporting.technical_report_service import TechnicalReportService
                            resolved_doc_path = TechnicalReportService.safe_resolve_storage_path(doc.stored_path)
                            if not resolved_doc_path:
                                errors.append(
                                    f"La evidencia para '{req.description or req.id}' referencia el documento {doc.id} ('{doc.original_filename}') cuyo archivo físico ('{doc.stored_path}') no es accesible o no existe en el almacenamiento autorizado en régimen P12_STRICT."
                                )

                    # Verificador registrado
                    if req_evidence.verified_by is None:
                        errors.append(
                            f"La evidencia para '{req.description or req.id}' no cuenta con usuario verificador registrado (verified_by nulo)."
                        )
                    else:
                        v_user = db.query(User).filter_by(id=req_evidence.verified_by, tenant_id=tenant_id).first()
                        if not v_user:
                            errors.append(
                                f"El usuario verificador {req_evidence.verified_by} no existe o no pertenece al tenant del expediente."
                            )

                if not has_verified and all_req_evidences:
                    errors.append(
                        f"Requerimiento obligatorio '{req.description or req.id}' no cuenta con ninguna evidencia en estado VERIFIED."
                    )

        # 7. Verificación de Elegibilidad VfM Real
        try:
            vfm_service = ValueForMoneyService(db)
            vfm_results = vfm_service.calculate_vfm(case_id)
            winning_vfm = next((item for item in vfm_results if item.get("supplier_offer_id") == winning_offer.id), None)
            if not winning_vfm:
                errors.append(f"La oferta ganadora #{winning_offer.id} no fue evaluada en el motor Value for Money (VfM).")
            elif not winning_vfm.get("is_eligible", False):
                errors.append(
                    f"La oferta ganadora #{winning_offer.id} no es elegible según Value for Money (VfM): {winning_vfm.get('reason', 'No elegible')}."
                )
        except Exception as e:
            errors.append(f"Fallo en la ejecución del motor Value for Money (VfM): {str(e)}")

        if errors:
            return {
                "status": "FAIL",
                "errors": errors,
                "case_id": case_id,
                "winner_offer_id": winning_offer.id if winning_offer else None
            }

        return {
            "status": "PASS",
            "errors": [],
            "case_id": case_id,
            "winner_offer_id": winning_offer.id,
            "attempt_id": attempt.id,
            "selection_final_id": selection_final.id,
            "traceability_regime": traceability_regime
        }
