from dataclasses import dataclass
from typing import List, Optional
import difflib
import re

from app.models.domain import EvaluationMethod
from app.services.comparison_engine.normalizers import (
    normalize_text_for_exact_match,
    normalize_text_for_fuzzy_match
)
from app.services.comparison_engine.extractors import extract_numeric_value

@dataclass
class MatchCandidate:
    quotation_section_id: int
    text: str
    evaluation_method: EvaluationMethod
    similarity_score: float
    page: Optional[int] = None
    required_numeric_value: Optional[float] = None
    found_numeric_value: Optional[float] = None
    numeric_unit: Optional[str] = None

class ComparisonMatcher:
    def __init__(self, quotation_sections: List[dict]):
        """
        quotation_sections: lista de diccionarios con la estructura:
        {'id': int, 'text': str, 'page': Optional[int]}
        """
        self.quotation_sections = quotation_sections
        self.fuzzy_length_limit = 1000
        
    def find_candidates(self, req_text: str) -> List[MatchCandidate]:
        candidates: List[MatchCandidate] = []
        
        req_exact = normalize_text_for_exact_match(req_text)
        req_fuzzy = normalize_text_for_fuzzy_match(req_text)
        req_numeric = extract_numeric_value(req_exact)
        
        for section in self.quotation_sections:
            sec_id = section['id']
            sec_text_raw = section['text']
            sec_page = section.get('page')
            
            if not sec_text_raw:
                continue
                
            sec_exact = normalize_text_for_exact_match(sec_text_raw)
            sec_fuzzy = normalize_text_for_fuzzy_match(sec_text_raw)
            
            # 1. Exact Match (Igualdad o subcadena)
            if req_exact and req_exact in sec_exact:
                candidates.append(MatchCandidate(
                    quotation_section_id=sec_id,
                    text=sec_text_raw,
                    evaluation_method=EvaluationMethod.EXACT_MATCH,
                    similarity_score=1.0,
                    page=sec_page
                ))
                continue # Si hay exact match, no necesitamos buscar más en esta sección
                
            # 2. Numeric Match
            sec_numeric = extract_numeric_value(sec_exact)
            if req_numeric and sec_numeric:
                req_val, req_unit = req_numeric
                sec_val, sec_unit = sec_numeric
                
                # Si ambos tienen unidad y es la misma, o si es un número válido de contexto similar
                if req_unit and sec_unit and req_unit == sec_unit:
                    # Calculamos ratio de contexto para asegurar que hablan de lo mismo
                    context_ratio = difflib.SequenceMatcher(None, req_fuzzy, sec_fuzzy).ratio()
                    
                    candidates.append(MatchCandidate(
                        quotation_section_id=sec_id,
                        text=sec_text_raw,
                        evaluation_method=EvaluationMethod.NUMERIC_MATCH,
                        similarity_score=max(0.8, context_ratio), # Le damos alto peso por coincidir la unidad
                        page=sec_page,
                        required_numeric_value=req_val,
                        found_numeric_value=sec_val,
                        numeric_unit=req_unit
                    ))
                    continue
            
            # 3. Fuzzy Match
            # Segmentar si es muy largo
            fragments = []
            if len(sec_fuzzy) > self.fuzzy_length_limit:
                # Segmentar por punto, salto de línea o coma si es muy largo
                raw_fragments = re.split(r'[.\n]', sec_text_raw)
                fragments = [f for f in raw_fragments if f.strip()]
            else:
                fragments = [sec_text_raw]
                
            best_fragment_score = 0.0
            best_fragment_text = ""
            
            for frag in fragments:
                frag_fuzzy = normalize_text_for_fuzzy_match(frag)
                if not frag_fuzzy or len(frag_fuzzy) > self.fuzzy_length_limit:
                    continue
                    
                score = difflib.SequenceMatcher(None, req_fuzzy, frag_fuzzy).ratio()
                if score > best_fragment_score:
                    best_fragment_score = score
                    best_fragment_text = frag.strip()
                    
            if best_fragment_score >= 0.40:
                candidates.append(MatchCandidate(
                    quotation_section_id=sec_id,
                    text=best_fragment_text,
                    evaluation_method=EvaluationMethod.FUZZY_MATCH,
                    similarity_score=best_fragment_score,
                    page=sec_page
                ))
                
        # Post-procesamiento: Eliminar duplicados, ordenar y limitar a 5
        unique_candidates = []
        seen = set()
        
        # Ordenar primero por score descendente
        candidates.sort(key=lambda x: x.similarity_score, reverse=True)
        
        for c in candidates:
            # Clave única: seccion + metodo + texto exacto encontrado
            key = (c.quotation_section_id, c.evaluation_method, c.text)
            if key not in seen:
                seen.add(key)
                unique_candidates.append(c)
                if len(unique_candidates) == 5:
                    break
                    
        return unique_candidates
