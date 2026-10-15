from sqlalchemy.orm import Session
from app.models.v6.supplier_profile import SupplierProfile
from app.models.v6.supplier_offer import SupplierOffer
from app.models.v6.supplier_selection import SupplierSelectionAttempt, SupplierSelectionFinal
from app.models.v6.case_workflow import CaseWorkflow
from app.models.domain import AuditLog, CaseFile

class SelectionService:
    @staticmethod
    def select_supplier(db: Session, offer_id: int, user_id: int, user_role: str, tenant_id: str, reason: str = ""):
        """
        Attempts to select an offer as the winner.
        Enforces that the supplier's validation_status must be VERIFIED.
        """
        offer = db.query(SupplierOffer).filter_by(id=offer_id).first()
        if not offer:
            raise ValueError("Offer not found")

        profile = db.query(SupplierProfile).filter_by(supplier_id=offer.supplier_id).first()
        if not profile:
            raise ValueError("Supplier Profile not found")

        if profile.validation_status != "VERIFIED":
            if profile.validation_status in ["REJECTED", "SANCTIONED", "BLOCKED"]:
                raise ValueError(f"Cannot select supplier with unfavorable status: {profile.validation_status}")
            if user_role == "SUPERVISOR":
                clean_reason = (reason or "").strip()
                if not clean_reason:
                    raise ValueError(f"Supervisor exception requires explicit justification for supplier status: {profile.validation_status}")
                # SUPERVISOR_EXCEPTION logic
                audit = AuditLog(
                    user_id=user_id,
                    tenant_id=tenant_id,
                    action="SUPERVISOR_EXCEPTION_SELECT",
                    entity_type="SupplierOffer",
                    entity_id=str(offer.id),
                    details=f"Supervisor bypassed validation_status {profile.validation_status}. Reason: {clean_reason}",
                    status="WARNING"
                )
                db.add(audit)
            else:
                raise PermissionError(f"Cannot select supplier with validation_status {profile.validation_status}. Supervisor override required.")

        # Proceed with selection...
        offer.status = "SELECTED"

        audit_sel = AuditLog(
            user_id=user_id,
            tenant_id=tenant_id,
            action="SELECT_SUPPLIER",
            entity_type="SupplierOffer",
            entity_id=str(offer.id),
            details="Offer selected as winner.",
            status="SUCCESS"
        )
        db.add(audit_sel)
        db.commit()
        return offer

    @staticmethod
    def propose_selection(
        db: Session,
        case_id: int,
        supplier_offer_id: int,
        justification: str,
        user_id: int,
        tenant_id: str,
        user_role: str = "OPERATOR"
    ):
        offer = db.query(SupplierOffer).filter_by(id=supplier_offer_id, case_id=case_id).first()
        if not offer:
            raise ValueError("Offer not found in this case")

        if offer.status == "PENDING":
            raise ValueError("Cannot select a PENDING offer")

        if offer.status in ["REJECTED", "OBSERVED"]:
            if user_role not in ["SUPERVISOR", "ADMIN"]:
                raise ValueError(f"Cannot select offer with status {offer.status}")

        # FASE 3: Integridad de la oferta y cobertura estricta de CaseProcurementItem
        from app.models.v6.case_procurement_item import CaseProcurementItem
        import math

        procurement_items = db.query(CaseProcurementItem).filter_by(case_id=case_id).all()
        if procurement_items:
            case_proc_ids = {pi.id for pi in procurement_items}
            proc_item_map = {pi.id: pi for pi in procurement_items}
            if not offer.items:
                raise ValueError("Incomplete offer: Missing items for procurement requirements")

            offered_proc_ids = set()
            calculated_total = 0.0

            for itm in offer.items:
                if itm.procurement_item_id is None:
                    raise ValueError(f"Incomplete offer: Item {itm.id} has no procurement item reference")
                if itm.procurement_item_id in offered_proc_ids:
                    raise ValueError(f"Incomplete offer: Duplicate procurement item reference {itm.procurement_item_id} in offer")
                if itm.procurement_item_id not in case_proc_ids:
                    raise ValueError(f"Invalid offer: Item quotes procurement_item_id {itm.procurement_item_id} which does not belong to case {case_id}")

                offered_proc_ids.add(itm.procurement_item_id)
                proc_req = proc_item_map[itm.procurement_item_id]

                if itm.unit_price is None:
                    raise ValueError(f"Incomplete offer: Item for procurement {itm.procurement_item_id} is missing unit price")
                try:
                    price_val = float(itm.unit_price)
                except (ValueError, TypeError):
                    raise ValueError(f"Incomplete offer: Item for procurement {itm.procurement_item_id} has non-numeric unit price")
                if math.isnan(price_val) or math.isinf(price_val) or price_val <= 0:
                    raise ValueError(f"Incomplete offer: Item for procurement {itm.procurement_item_id} has non-positive or non-finite unit price")

                if itm.quantity is None:
                    raise ValueError(f"Incomplete offer: Item for procurement {itm.procurement_item_id} is missing quantity")
                try:
                    qty_val = float(itm.quantity)
                except (ValueError, TypeError):
                    raise ValueError(f"Incomplete offer: Item for procurement {itm.procurement_item_id} has non-numeric quantity")
                if math.isnan(qty_val) or math.isinf(qty_val) or qty_val <= 0:
                    raise ValueError(f"Incomplete offer: Item for procurement {itm.procurement_item_id} has non-positive or non-finite quantity")

                # Correspondencia entre cantidades requeridas y ofertadas
                if proc_req.quantity is not None:
                    try:
                        req_qty_val = float(proc_req.quantity)
                    except (ValueError, TypeError):
                        req_qty_val = None
                    if req_qty_val is not None and abs(qty_val - req_qty_val) > 1e-4:
                        raise ValueError(f"Quantity mismatch: Item for procurement {itm.procurement_item_id} offered quantity ({qty_val}) does not match required quantity ({req_qty_val})")

                calculated_total += (price_val * qty_val)

            missing_proc_ids = case_proc_ids - offered_proc_ids
            if missing_proc_ids:
                raise ValueError(f"Incomplete offer: Missing coverage for required procurement items: {sorted(list(missing_proc_ids))}")

        # Comprobación de precio total de la oferta
        raw_price = offer.total_amount if offer.total_amount is not None else offer.price
        if raw_price is not None:
            try:
                total_price_val = float(raw_price)
            except (ValueError, TypeError):
                raise ValueError("Incomplete offer: Offer total price is non-numeric")
            if math.isnan(total_price_val) or math.isinf(total_price_val) or total_price_val <= 0:
                raise ValueError(f"Incomplete offer: Offer total price {total_price_val} is invalid or non-positive")
        elif procurement_items:
            raise ValueError("Incomplete offer: Offer has no total price defined")

        # Consistencia entre subtotales y total económico declarado
        if procurement_items and raw_price is not None:
            try:
                hdr_total = float(raw_price)
            except (ValueError, TypeError):
                hdr_total = None
            if hdr_total is not None and abs(hdr_total - calculated_total) > 0.05:
                raise ValueError(f"Inconsistent offer total amount: Header total ({hdr_total}) does not match sum of item subtotals ({calculated_total})")

        # Impedir comparaciones o selecciones entre monedas heterogéneas sin regla de conversión
        case_offers = db.query(SupplierOffer).filter_by(case_id=case_id).all()
        distinct_currencies = {o.currency for o in case_offers if o.currency}
        if len(distinct_currencies) > 1:
            raise ValueError(f"Incompatible currencies in case ({sorted(list(distinct_currencies))}): Direct comparison or selection between heterogeneous currencies is not permitted without an explicit conversion rule.")

        # Verify supplier validation status
        profile = db.query(SupplierProfile).filter_by(supplier_id=offer.supplier_id).first()
        val_status = profile.validation_status if profile else "UNAVAILABLE"

        if val_status != "VERIFIED":
            if val_status in ["REJECTED", "SANCTIONED", "BLOCKED"]:
                raise ValueError(f"Cannot select supplier with unfavorable status: {val_status}")

            clean_just = (justification or "").strip()
            if user_role in ["SUPERVISOR", "ADMIN"]:
                if not clean_just:
                    raise ValueError(f"Supervisor exception requires explicit justification for supplier status: {val_status}")
                audit_warn = AuditLog(
                    user_id=user_id,
                    tenant_id=tenant_id,
                    action="SUPERVISOR_EXCEPTION_SELECT",
                    entity_type="SupplierOffer",
                    entity_id=str(offer.id),
                    details=f"Supervisor proposed offer for unverified supplier ({val_status}). Justification: {clean_just}",
                    status="WARNING"
                )
                db.add(audit_warn)
            else:
                raise ValueError(f"Cannot select supplier with validation_status {val_status}. Supervisor override required.")

        # FASE 4: Elegibilidad individual obligatoria y recomendación referencial VfM
        from app.services.v6.evaluation.vfm_service import ValueForMoneyService
        from app.models.v6.case_requirement_matrix import CaseRequirementMatrix
        matrix_reqs = db.query(CaseRequirementMatrix).filter_by(case_id=case_id, mandatory=True).all()
        mandatory_req_ids = {r.id for r in matrix_reqs}

        vfm_service = ValueForMoneyService(db)
        vfm_results = vfm_service.calculate_vfm(case_id)
        clean_justification = (justification or "").strip()

        # 1. Obtener resultado de evaluación correspondiente a la oferta propuesta
        current_vfm = next((r for r in vfm_results if r.get("supplier_offer_id") == offer.id), None)

        # 2. Comprobar su elegibilidad obligatoria independientemente de que existan otras ofertas recomendadas
        if current_vfm:
            if not current_vfm.get("is_eligible"):
                reason = current_vfm.get("reason", "UNKNOWN")
                if reason in ("FAILED_CONTRACTUAL_CONDITIONS", "FAILED_MANDATORY_REQUIREMENTS"):
                    raise ValueError("Cannot propose an ineligible offer: Failed mandatory contractual conditions.")
                elif reason == "CONFLICT_MANDATORY_REQUIREMENTS":
                    raise ValueError("Cannot propose an ineligible offer: Mandatory requirement evaluation has unresolved conflicts (CONFLICT).")
                elif reason == "MISSING_DATA_MANDATORY_REQUIREMENTS":
                    raise ValueError("Cannot propose an ineligible offer: Mandatory requirement evaluation has missing data (MISSING_DATA).")
                elif reason == "OBSERVED_MANDATORY_REQUIREMENTS":
                    raise ValueError("Cannot propose an ineligible offer: Mandatory requirement evaluation has unresolved observations (OBSERVED).")
                elif reason in ("MANDATORY_EVALUATIONS_PENDING", "UNRESOLVED_MANDATORY_REQUIREMENTS"):
                    raise ValueError("Cannot propose an offer with pending mandatory evaluations.")
                elif reason == "INCOMPATIBLE_CURRENCIES_NO_CONVERSION_RULE":
                    raise ValueError("Cannot propose offer: Incompatible currencies in case without conversion rule.")
                elif reason == "NOT_EVALUATED":
                    has_evaluated_offers = any(r.get("is_evaluated") for r in vfm_results)
                    if has_evaluated_offers or mandatory_req_ids:
                        raise ValueError("Cannot propose an unevaluated offer: Mandatory evaluations are pending.")
                    elif not clean_justification:
                        raise ValueError("Justification is required when proposing an unevaluated offer.")
                else:
                    raise ValueError(f"Cannot propose an ineligible offer ({reason}).")
        else:
            raise ValueError("Cannot propose offer: No evaluation results found for this offer.")

        # 3. Recomendación referencial del sistema
        reliable_recommendations = [
            r for r in vfm_results
            if r.get("is_eligible") and (r.get("total_score") or 0) > 0 and (r.get("price") or 0) > 0
        ]

        is_divergent = False

        if reliable_recommendations:
            top_rec_id = reliable_recommendations[0]["supplier_offer_id"]
            if offer.id != top_rec_id:
                is_divergent = True
                if not clean_justification:
                    raise ValueError("Justification is required when proposing an offer different from the top recommended offer")
        else:
            # When no reliable objective recommendation exists from the system
            if not clean_justification:
                raise ValueError("Justification is required when proposing an offer without a valid system recommendation")

        existing_final = db.query(SupplierSelectionFinal).filter_by(case_id=case_id).first()
        if existing_final:
            raise ValueError("Supplier selection has already been finalized for this case")

        clean_justification = justification.strip() if justification else None
        attempt = SupplierSelectionAttempt(
            case_id=case_id,
            supplier_offer_id=supplier_offer_id,
            justification_comment=clean_justification,
            selected_by=user_id,
            status="UNDER_REVIEW"
        )
        db.add(attempt)

        workflow = db.query(CaseWorkflow).filter_by(case_id=case_id).first()
        if not workflow:
            workflow = CaseWorkflow(case_id=case_id, status="UNDER_REVIEW")
            db.add(workflow)
        else:
            workflow.status = "UNDER_REVIEW"

        audit = AuditLog(
            user_id=user_id,
            tenant_id=tenant_id,
            action="PROPOSE_SELECTION",
            entity_type="CaseFile",
            entity_id=str(case_id),
            details=f"Selection proposed for offer {supplier_offer_id}. Divergent: {is_divergent}.",
            status="SUCCESS"
        )
        db.add(audit)
        db.commit()
        return attempt

    @staticmethod
    def approve_selection(db: Session, case_id: int, supervisor_id: int, tenant_id: str):
        # Bloqueo a nivel de fila sobre el caso para sincronizar con la persistencia asíncrona de workers
        locked_case = (
            db.query(CaseFile)
            .filter(CaseFile.id == case_id)
            .populate_existing()
            .with_for_update()
            .first()
        )
        if not locked_case:
            raise ValueError(f"Case {case_id} not found")

        # 1. El expediente pertenece al tenant solicitado
        if locked_case.tenant_id != tenant_id:
            raise ValueError(f"Case {case_id} does not belong to tenant {tenant_id}")

        # 2. El estado vuelve a comprobarse después de adquirir el bloqueo
        # 3. No se degrada ni sobrescribe un estado terminal previo
        if locked_case.status in ["APPROVED", "COMPLETED"]:
            raise ValueError(f"Case is already in terminal status: {locked_case.status}")

        existing_final = db.query(SupplierSelectionFinal).filter_by(case_id=case_id).first()
        if existing_final:
            raise ValueError("Supplier selection has already been finalized for this case")

        # 4. Existe una transición legítima de aprobación
        workflow = db.query(CaseWorkflow).filter_by(case_id=case_id).first()
        if workflow and workflow.status in ["APPROVED", "COMPLETED"]:
            raise ValueError(f"Workflow is already in terminal status: {workflow.status}")

        attempt = (
            db.query(SupplierSelectionAttempt)
            .filter_by(case_id=case_id, status="UNDER_REVIEW")
            .order_by(SupplierSelectionAttempt.id.desc())
            .first()
        )
        if not attempt:
            raise ValueError("No proposed selection found for this case in UNDER_REVIEW status")

        # 5. El cambio de CaseFile, CaseWorkflow y SupplierSelectionFinal se confirma de manera atómica
        locked_case.status = "APPROVED"

        final = SupplierSelectionFinal(case_id=case_id, attempt_id=attempt.id)
        db.add(final)

        if not workflow:
            workflow = CaseWorkflow(case_id=case_id, status="APPROVED", supervisor_id=supervisor_id)
            db.add(workflow)
        else:
            workflow.status = "APPROVED"
            workflow.supervisor_id = supervisor_id

        audit = AuditLog(
            user_id=supervisor_id,
            tenant_id=tenant_id,
            action="APPROVE_SELECTION",
            entity_type="CaseFile",
            entity_id=str(case_id),
            details="Selection approved.",
            status="SUCCESS"
        )
        db.add(audit)
        db.commit()
        return final
