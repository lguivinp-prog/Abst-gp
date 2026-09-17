from typing import List, Dict, Any
from sqlalchemy.orm import Session
from app.models.v6.case_requirement_matrix import CaseRequirementMatrix
from app.models.v6.supplier_offer_contract_term import SupplierOfferContractTerm
from app.models.v6.contractual_condition import ContractualCondition

class ContractualResolver:
    def __init__(self, db: Session):
        self.db = db

    def resolve_offer(self, offer_id: int, requirements: List[CaseRequirementMatrix]) -> List[ContractualCondition]:
        offer_terms = self.db.query(SupplierOfferContractTerm).filter_by(supplier_offer_id=offer_id).all()
        term_map = {t.key: t for t in offer_terms if t.key}

        conditions = []
        for req in requirements:
            if req.requirement_type != "CONTRACTUAL":
                continue

            key = req.key
            if not key:
                continue

            term = term_map.get(key)

            # Evaluate
            status = "REQUIERE_REVISION"
            rule = "MANUAL_REVIEW_REQUIRED"
            offered_val = None
            final_val = req.value

            if term:
                offered_val = term.value_text

                if req.numeric_value is not None and term.numeric_value is not None:
                    if req.comparator == "MAX":
                        if term.numeric_value <= req.numeric_value:
                            if term.numeric_value < req.numeric_value:
                                status = "CUMPLE_Y_MEJORA"
                                rule = "OFFER_IMPROVEMENT"
                            else:
                                status = "CUMPLE"
                                rule = "EXACT_MATCH"
                            final_val = term.value_text
                        else:
                            status = "NO_CUMPLE"
                            rule = "REQUIREMENT_DEFAULT"
                            final_val = req.value
                    elif req.comparator == "MIN":
                        if term.numeric_value >= req.numeric_value:
                            if term.numeric_value > req.numeric_value:
                                status = "CUMPLE_Y_MEJORA"
                                rule = "OFFER_IMPROVEMENT"
                            else:
                                status = "CUMPLE"
                                rule = "EXACT_MATCH"
                            final_val = term.value_text
                        else:
                            status = "NO_CUMPLE"
                            rule = "REQUIREMENT_DEFAULT"
                            final_val = req.value
                    elif req.comparator == "EXACT":
                        if term.numeric_value == req.numeric_value:
                            status = "CUMPLE"
                            rule = "EXACT_MATCH"
                            final_val = term.value_text
                        else:
                            status = "NO_CUMPLE"
                            rule = "REQUIREMENT_DEFAULT"
                            final_val = req.value
                    elif req.comparator == "RANGE":
                        required_min = None
                        required_max = None

                        if req.value:
                            import re
                            # Extract numbers from "10-20", "10 a 20", etc.
                            matches = re.findall(r'(\d+(?:\.\d+)?)', req.value)
                            if len(matches) >= 2:
                                required_min = float(matches[0])
                                required_max = float(matches[1])
                                if required_min > required_max:
                                    required_min, required_max = required_max, required_min

                        if required_min is None or required_max is None:
                            status = "REQUIERE_REVISION"
                            rule = "MANUAL_REVIEW_REQUIRED"
                            final_val = req.value
                        else:
                            if term.numeric_value < required_min:
                                status = "NO_CUMPLE"
                                rule = "OUT_OF_RANGE_BELOW"
                            elif term.numeric_value > required_max:
                                status = "NO_CUMPLE"
                                rule = "OUT_OF_RANGE_ABOVE"
                            else:
                                status = "CUMPLE"
                                rule = "IN_RANGE"
                            final_val = term.value_text
                elif req.comparator == "TEXT":
                    if term.value_text and term.value_text.strip().lower() == req.value.strip().lower():
                        status = "CUMPLE"
                        rule = "EXACT_MATCH"
                        final_val = term.value_text
                    else:
                        status = "NO_CUMPLE"
                        rule = "REQUIREMENT_DEFAULT"
            else:
                status = "NO_OFERTADO"
                rule = "MISSING_DATA"

            cond = ContractualCondition(
                supplier_offer_id=offer_id,
                key=key,
                label=req.description,
                required_value=req.value,
                offered_value=offered_val,
                final_value=final_val,
                unit=req.unit,
                resolution_rule=rule,
                status=status
            )
            self.db.add(cond)
            conditions.append(cond)

        self.db.commit()
        return conditions
