from dataclasses import dataclass
from typing import List, Optional
import re

from app.models.domain import ComparisonResultStatus, EvaluationMethod
from app.services.comparison_engine.matcher import MatchCandidate
from app.services.comparison_engine.normalizers import normalize_text_for_exact_match
from app.services.comparison_engine.extractors import extract_numeric_value

@dataclass
class ScoringDecision:
    status: ComparisonResultStatus
    confidence_score: float
    evaluation_method: EvaluationMethod
    selected_candidate: Optional[MatchCandidate]
    reasoning: str

class ComparisonScorer:
    def __init__(self):
        # Operadores
        self.min_modifiers = ["mínimo", "minimo", "al menos", "no menor de", "igual o mayor", "desde"]
        self.max_modifiers = ["máximo", "maximo", "hasta", "no mayor de", "igual o menor"]
        self.exact_modifiers = ["exactamente", "igual a", "debe ser"]
        
        # Negaciones
        self.negations = [" no ", " sin ", " no incluye ", " no cumple ", " excepto ", " excluye "]

    def _has_negation(self, text: str) -> bool:
        normalized = f" {normalize_text_for_exact_match(text)} "
        for neg in self.negations:
            if neg in normalized:
                return True
        return False

    def _determine_numeric_operator(self, req_text: str) -> str:
        normalized = normalize_text_for_exact_match(req_text)
        for mod in self.min_modifiers:
            if mod in normalized:
                return ">="
        for mod in self.max_modifiers:
            if mod in normalized:
                return "<="
        for mod in self.exact_modifiers:
            if mod in normalized:
                return "=="
        return "unknown"

    def evaluate(self, req_text: str, candidates: List[MatchCandidate]) -> ScoringDecision:
        if not candidates:
            return ScoringDecision(
                status=ComparisonResultStatus.FAIL,
                confidence_score=0.2,
                evaluation_method=EvaluationMethod.NO_MATCH,
                selected_candidate=None,
                reasoning="No se encontró evidencia de cumplimiento en la cotización."
            )
            
        # Evaluar individualmente cada candidato
        decisions = []
        for c in candidates:
            decisions.append(self._evaluate_single_candidate(req_text, c))
            
        # Descartar candidatos irrelevantes (Fuzzy < 0.60)
        valid_decisions = [d for d in decisions if d.confidence_score >= 0.60]
        
        if not valid_decisions:
            return ScoringDecision(
                status=ComparisonResultStatus.FAIL,
                confidence_score=0.2,
                evaluation_method=EvaluationMethod.NO_MATCH,
                selected_candidate=None,
                reasoning="No se encontró evidencia suficiente de cumplimiento en la cotización."
            )
            
        # Ordenar por puntaje (mejor evidencia primero)
        valid_decisions.sort(key=lambda x: x.confidence_score, reverse=True)
        best_decision = valid_decisions[0]
        
        # Detectar contradicciones
        passes = [d for d in valid_decisions if d.status == ComparisonResultStatus.PASS]
        fails = [d for d in valid_decisions if d.status == ComparisonResultStatus.FAIL]
        
        # Si hay candidatos con evidencias de PASS y otros con FAIL, es contradictorio
        if passes and fails:
            return ScoringDecision(
                status=ComparisonResultStatus.MANUAL_REVIEW,
                confidence_score=0.65,
                evaluation_method=EvaluationMethod.MANUAL_REVIEW,
                selected_candidate=best_decision.selected_candidate,
                reasoning="Se encontraron evidencias contradictorias dentro de la cotización."
            )
            
        return best_decision

    def _evaluate_single_candidate(self, req_text: str, candidate: MatchCandidate) -> ScoringDecision:
        has_negation = self._has_negation(candidate.text)
        
        if has_negation:
            # Una negación explícita es un FAIL claro, pero lo marcamos MANUAL_REVIEW si la lógica es dudosa
            return ScoringDecision(
                status=ComparisonResultStatus.FAIL,
                confidence_score=0.90,
                evaluation_method=candidate.evaluation_method,
                selected_candidate=candidate,
                reasoning="Se encontró evidencia explícita de negación o exclusión en la cotización."
            )

        if candidate.evaluation_method == EvaluationMethod.NUMERIC_MATCH:
            op = self._determine_numeric_operator(req_text)
            req_val = candidate.required_numeric_value
            found_val = candidate.found_numeric_value
            
            if req_val is not None and found_val is not None:
                if op == ">=":
                    if found_val >= req_val:
                        return ScoringDecision(ComparisonResultStatus.PASS, 0.95, EvaluationMethod.NUMERIC_MATCH, candidate, f"El valor encontrado ({found_val}) es mayor o igual al requerido ({req_val}).")
                    else:
                        return ScoringDecision(ComparisonResultStatus.FAIL, 0.90, EvaluationMethod.NUMERIC_MATCH, candidate, f"El valor encontrado ({found_val}) es menor al mínimo requerido ({req_val}).")
                elif op == "<=":
                    if found_val <= req_val:
                        return ScoringDecision(ComparisonResultStatus.PASS, 0.95, EvaluationMethod.NUMERIC_MATCH, candidate, f"El valor encontrado ({found_val}) es menor o igual al máximo permitido ({req_val}).")
                    else:
                        return ScoringDecision(ComparisonResultStatus.FAIL, 0.90, EvaluationMethod.NUMERIC_MATCH, candidate, f"El valor encontrado ({found_val}) excede el máximo permitido ({req_val}).")
                elif op == "==":
                    if found_val == req_val:
                        return ScoringDecision(ComparisonResultStatus.PASS, 0.95, EvaluationMethod.NUMERIC_MATCH, candidate, f"El valor encontrado ({found_val}) es exactamente igual al requerido ({req_val}).")
                    else:
                        return ScoringDecision(ComparisonResultStatus.FAIL, 0.90, EvaluationMethod.NUMERIC_MATCH, candidate, f"El valor encontrado ({found_val}) difiere del requerido ({req_val}).")
                else: # unknown
                    if found_val == req_val:
                        return ScoringDecision(ComparisonResultStatus.PASS, 0.90, EvaluationMethod.NUMERIC_MATCH, candidate, f"El valor encontrado coincide con el requerido sin modificador explícito.")
                    else:
                        return ScoringDecision(ComparisonResultStatus.MANUAL_REVIEW, 0.65, EvaluationMethod.NUMERIC_MATCH, candidate, f"Se encontraron valores diferentes ({req_val} vs {found_val}) sin un modificador de tolerancia claro.")
                        
        if candidate.evaluation_method == EvaluationMethod.EXACT_MATCH:
            return ScoringDecision(
                status=ComparisonResultStatus.PASS,
                confidence_score=1.0,
                evaluation_method=EvaluationMethod.EXACT_MATCH,
                selected_candidate=candidate,
                reasoning="Coincidencia textual exacta validada (sin negaciones)."
            )
            
        if candidate.evaluation_method == EvaluationMethod.FUZZY_MATCH:
            score = candidate.similarity_score
            
            # Safety check: ¿Los números coinciden si es que hay números?
            req_numeric = extract_numeric_value(req_text)
            can_numeric = extract_numeric_value(candidate.text)
            
            if req_numeric and can_numeric:
                if req_numeric[0] != can_numeric[0] or req_numeric[1] != can_numeric[1]:
                    return ScoringDecision(
                        status=ComparisonResultStatus.MANUAL_REVIEW,
                        confidence_score=0.65,
                        evaluation_method=EvaluationMethod.FUZZY_MATCH,
                        selected_candidate=candidate,
                        reasoning="Alta similitud textual pero difieren en los valores numéricos o unidades detectadas."
                    )
                
            if score >= 0.85:
                return ScoringDecision(ComparisonResultStatus.PASS, score, EvaluationMethod.FUZZY_MATCH, candidate, "Similitud textual alta sin diferencias críticas.")
            elif score >= 0.60:
                return ScoringDecision(ComparisonResultStatus.MANUAL_REVIEW, score, EvaluationMethod.FUZZY_MATCH, candidate, "Similitud textual intermedia (ambigua).")
            else:
                return ScoringDecision(ComparisonResultStatus.FAIL, score, EvaluationMethod.NO_MATCH, None, "Similitud insuficiente para considerarse evidencia confiable.")
                
        return ScoringDecision(ComparisonResultStatus.MANUAL_REVIEW, 0.65, EvaluationMethod.NO_MATCH, candidate, "Candidato no evaluado formalmente.")

