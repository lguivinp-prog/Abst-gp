from typing import Dict, Any, List
from app.services.extraction_engine.models.document import StructuredDocument
from app.services.extraction_engine.config import ocr_config, contract_config

class OcrEvaluator:
    def __init__(self):
        # Usamos CONTRACT_DOCUMENT_WEIGHTS para contratos
        self.weights = ocr_config.CONTRACT_DOCUMENT_WEIGHTS
        self.expected_sections = contract_config.EXPECTED_SECTIONS_BIENES

    def evaluate(self, document: StructuredDocument) -> Dict[str, Any]:
        text_score = self._evaluate_text(document)
        layout_score = self._evaluate_layout(document)
        table_score = self._evaluate_tables(document)
        semantic_score, section_detection_rate = self._evaluate_semantic(document)
        
        overall = (
            text_score * self.weights["text"] +
            layout_score * self.weights["layout"] +
            table_score * self.weights["table"] +
            semantic_score * self.weights["semantic"]
        )
        
        state = "APPROVED"
        reasons = []
        
        if overall < ocr_config.SCORE_THRESHOLDS["REVIEW_REQUIRED"]:
            state = "FAILED"
            reasons.append(f"Score general ({overall:.2f}) por debajo de {ocr_config.SCORE_THRESHOLDS['REVIEW_REQUIRED']}.")
        elif overall < ocr_config.SCORE_THRESHOLDS["APPROVED"]:
            state = "REVIEW_REQUIRED"
            reasons.append(f"Score general ({overall:.2f}) requiere revisión manual.")
            
        if text_score < ocr_config.MIN_TEXT_CONFIDENCE:
            if state == "APPROVED": state = "REVIEW_REQUIRED"
            reasons.append(f"Calidad de texto ({text_score:.2f}) por debajo del mínimo de {ocr_config.MIN_TEXT_CONFIDENCE}.")
            
        return {
            "score": round(overall, 3),
            "details": {
                "text_quality": round(text_score, 3),
                "layout_quality": round(layout_score, 3),
                "table_quality": round(table_score, 3),
                "semantic_quality": round(semantic_score, 3),
                "section_detection_rate": round(section_detection_rate, 3)
            },
            "state": state,
            "reasons": reasons
        }
        
    def _evaluate_text(self, document: StructuredDocument) -> float:
        total_conf = 0.0
        count = 0
        for block in document.blocks:
            for elem in getattr(block, "source_elements", []):
                total_conf += elem.confidence
                count += 1
        if count == 0:
            return 1.0
        return total_conf / count
        
    def _evaluate_layout(self, document: StructuredDocument) -> float:
        if not document.pages:
            return 0.0
        ratio = len(document.blocks) / len(document.pages)
        if ratio > 10:
            return 0.95
        elif ratio > 5:
            return 0.80
        return 0.50
        
    def _evaluate_tables(self, document: StructuredDocument) -> float:
        if not document.tables:
            return 1.0 
            
        total_conf = sum(t.confidence for t in document.tables)
        return total_conf / len(document.tables)
        
    def _evaluate_semantic(self, document: StructuredDocument) -> tuple[float, float]:
        found = set()
        for block in document.blocks:
            if block.type == "section" and block.normalized_text:
                found.add(block.normalized_text)
                
        count = 0
        for section in self.expected_sections:
            if any(section in f for f in found):
                count += 1
        
        if len(self.expected_sections) == 0:
            return 1.0, 1.0
            
        # Un documento real rara vez tiene las 14 secciones de la plantilla.
        # Asumimos que un contrato estándar de bienes tiene en promedio 6-7 secciones clave.
        realistic_max = 6.0 
        ratio = min(count / realistic_max, 1.0)
        
        # El score semántico es equivalente al ratio de detección sobre las esperadas reales
        semantic_score = ratio
        
        return semantic_score, ratio
