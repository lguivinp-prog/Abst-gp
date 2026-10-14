from typing import List, Dict, Any
from sqlalchemy.orm import Session
from app.models.v6.supplier_offer import SupplierOffer
from app.models.v6.evaluation_factor import EvaluationFactor
from app.models.v6.contractual_condition import ContractualCondition
from app.models.v6.supplier_offer_contract_term import SupplierOfferContractTerm

class ValueForMoneyService:
    def __init__(self, db: Session):
        self.db = db

    def calculate_vfm(self, case_id: int) -> List[Dict[str, Any]]:
        # 1. Get all offers for the case
        offers = self.db.query(SupplierOffer).filter_by(case_id=case_id).all()

        # 2. Get evaluation factors
        factors = self.db.query(EvaluationFactor).filter_by(case_id=case_id).all()

        # Impedir comparaciones económicas entre monedas heterogéneas sin regla de conversión
        distinct_currencies = {offer.currency for offer in offers if offer.currency}
        has_incompatible_currencies = len(distinct_currencies) > 1

        # Comprobar requerimientos obligatorios registrados en el expediente
        from app.models.v6.case_requirement_matrix import CaseRequirementMatrix
        mandatory_reqs = self.db.query(CaseRequirementMatrix).filter_by(case_id=case_id, mandatory=True).all()
        mandatory_req_ids = {r.id for r in mandatory_reqs}

        # Comprobar si existen condiciones contractuales registradas para alguna oferta del expediente
        all_case_offer_ids = [o.id for o in offers]
        case_has_conditions = self.db.query(ContractualCondition).filter(
            ContractualCondition.supplier_offer_id.in_(all_case_offer_ids)
        ).first() is not None if all_case_offer_ids else False

        results = []
        for offer in offers:
            # Check if offer is in pending/rejected/observed status
            if offer.status in ["REJECTED", "OBSERVED", "PENDING"]:
                results.append({
                    "supplier_offer_id": offer.id,
                    "supplier_id": offer.supplier_id,
                    "is_eligible": False,
                    "is_evaluated": False,
                    "total_score": 0.0,
                    "price": float(offer.total_amount) if offer.total_amount else (offer.price or 0.0),
                    "reason": f"OFFER_STATUS_{offer.status}"
                })
                continue

            if has_incompatible_currencies:
                results.append({
                    "supplier_offer_id": offer.id,
                    "supplier_id": offer.supplier_id,
                    "is_eligible": False,
                    "is_evaluated": False,
                    "total_score": 0.0,
                    "price": float(offer.total_amount) if offer.total_amount else (offer.price or 0.0),
                    "reason": "INCOMPATIBLE_CURRENCIES_NO_CONVERSION_RULE"
                })
                continue

            # Consultar evaluaciones de requerimientos para esta oferta
            from app.models.v6.offer_evaluation import OfferEvaluation
            offer_evals = self.db.query(OfferEvaluation).filter_by(supplier_offer_id=offer.id).all()

            # Comprobar que todas las evaluaciones de requisitos obligatorios estén concluidas
            if mandatory_req_ids:
                evaluated_req_ids = {e.requirement_id for e in offer_evals if e.status not in ["PENDING", None]}
                if mandatory_req_ids - evaluated_req_ids:
                    results.append({
                        "supplier_offer_id": offer.id,
                        "supplier_id": offer.supplier_id,
                        "is_eligible": False,
                        "is_evaluated": False,
                        "total_score": 0.0,
                        "price": float(offer.total_amount) if offer.total_amount else (offer.price or 0.0),
                        "reason": "MANDATORY_EVALUATIONS_PENDING"
                    })
                    continue

            # Comprobar si alguna evaluación técnica obligatoria resultó descalificada
            failed_evals = [e for e in offer_evals if e.status in ["FAILED", "REJECTED"]]
            if failed_evals:
                results.append({
                    "supplier_offer_id": offer.id,
                    "supplier_id": offer.supplier_id,
                    "is_eligible": False,
                    "is_evaluated": True,
                    "total_score": 0.0,
                    "price": float(offer.total_amount) if offer.total_amount else (offer.price or 0.0),
                    "reason": "FAILED_MANDATORY_REQUIREMENTS"
                })
                continue

            # Query contractual conditions for evaluation
            conditions = self.db.query(ContractualCondition).filter_by(supplier_offer_id=offer.id).all()

            # Si no cuenta con condiciones contractuales ni evaluaciones de requisitos, la oferta no fue evaluada
            if not conditions and not offer_evals:
                results.append({
                    "supplier_offer_id": offer.id,
                    "supplier_id": offer.supplier_id,
                    "is_eligible": False,
                    "is_evaluated": False,
                    "total_score": 0.0,
                    "price": float(offer.total_amount) if offer.total_amount else (offer.price or 0.0),
                    "reason": "NOT_EVALUATED"
                })
                continue

            failed_conditions = self.db.query(ContractualCondition).filter(
                ContractualCondition.supplier_offer_id == offer.id,
                ContractualCondition.status.in_(["NO_CUMPLE", "NO_OFERTADO", "REQUIERE_REVISION", "MISSING_DATA"])
            ).count()

            if failed_conditions > 0:
                results.append({
                    "supplier_offer_id": offer.id,
                    "supplier_id": offer.supplier_id,
                    "is_eligible": False,
                    "is_evaluated": True,
                    "total_score": 0.0,
                    "price": float(offer.total_amount) if offer.total_amount else (offer.price or 0.0),
                    "reason": "FAILED_CONTRACTUAL_CONDITIONS"
                })
                continue

            # Calculate score based on verified conditions and passed evaluations
            total_score = 0.0
            for cond in conditions:
                if cond.status == "CUMPLE_Y_MEJORA":
                    total_score += 10.0 # Bonus for improvement
                elif cond.status == "CUMPLE":
                    total_score += 5.0

            for ev in offer_evals:
                if ev.status == "PASSED":
                    total_score += 5.0

            raw_price = offer.total_amount if offer.total_amount is not None else offer.price
            price = float(raw_price) if raw_price is not None else 0.0

            if price > 0 and total_score > 0:
                vfm_ratio = price / total_score
            else:
                vfm_ratio = price if price > 0 else 0.0

            results.append({
                "supplier_offer_id": offer.id,
                "supplier_id": offer.supplier_id,
                "is_eligible": True,
                "is_evaluated": True,
                "total_score": total_score,
                "price": price,
                "vfm_ratio": vfm_ratio
            })

        # Separate eligible and ineligible
        eligible_results = [r for r in results if r["is_eligible"]]
        ineligible_results = [r for r in results if not r["is_eligible"]]

        eligible_results.sort(key=lambda x: x.get("vfm_ratio", float('inf')))

        return eligible_results + ineligible_results

    def compare(self, baseline_offer: SupplierOffer, compared_offer: SupplierOffer) -> Dict[str, Any]:
        baseline_price = float(baseline_offer.total_amount) if baseline_offer.total_amount else 0.0
        compared_price = float(compared_offer.total_amount) if compared_offer.total_amount else 0.0

        # We query the actual DB for terms
        baseline_terms = self.db.query(SupplierOfferContractTerm).filter_by(supplier_offer_id=baseline_offer.id).all()
        compared_terms = self.db.query(SupplierOfferContractTerm).filter_by(supplier_offer_id=compared_offer.id).all()

        b_map = {t.key: t.numeric_value for t in baseline_terms if t.key}
        c_map = {t.key: t.numeric_value for t in compared_terms if t.key}

        def calc_delta(b_val, c_val):
            if b_val is None or c_val is None:
                return None, None
            abs_delta = c_val - b_val
            pct_delta = (abs_delta / b_val * 100) if b_val != 0 else None
            return abs_delta, pct_delta

        p_abs, p_pct = calc_delta(baseline_price, compared_price)

        def term_dict(key):
            abs_d, pct_d = calc_delta(b_map.get(key), c_map.get(key))
            if abs_d is None:
                return None
            return {
                "baseline": b_map.get(key),
                "compared": c_map.get(key),
                "absolute_delta": abs_d,
                "percent_delta": pct_d
            }

        result = {
            "price": {
                "baseline": baseline_price,
                "compared": compared_price,
                "absolute_delta": p_abs,
                "percent_delta": p_pct
            },
            "delivery_term": term_dict("plazo") or term_dict("plazo_entrega"),
            "warranty": term_dict("garantia"),
            "useful_life": term_dict("vida_util"),
            "automatic_winner": "NONE"
        }

        # clean out Nones if they didn't exist in BOTH
        result = {k: v for k, v in result.items() if v is not None}
        return result
