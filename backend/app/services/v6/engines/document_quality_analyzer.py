from sqlalchemy.orm import Session
from app.models.v6.document_quality import DocumentQualityAssessment, DocumentQualityThresholdConfig
from typing import Dict, Any, List

class DocumentQualityAnalyzer:
    def __init__(self, db: Session):
        self.config = db.query(DocumentQualityThresholdConfig).first()
        if not self.config:
            self.config = DocumentQualityThresholdConfig() # Use defaults

    def analyze(self, document_id: int, mock_pdf_metrics: Dict[str, Any]) -> DocumentQualityAssessment:
        """
        Deterministically analyzes document quality without LLM.
        mock_pdf_metrics simulate the OpenCV/Tesseract pre-analysis output.
        """
        issues = []
        status = "QUALITY_GOOD"
        
        dpi = mock_pdf_metrics.get("dpi", 300)
        blur = mock_pdf_metrics.get("blur_score", 500.0)
        rotation = mock_pdf_metrics.get("rotation_degrees", 0.0)
        contrast = mock_pdf_metrics.get("contrast_ratio", 10.0)
        is_empty = mock_pdf_metrics.get("empty_pages", False)
        
        if is_empty:
            issues.append({"type": "EMPTY_PAGES", "desc": "El documento contiene paginas en blanco o sin texto estructurado."})
            status = "QUALITY_BLOCKED"
            
        if dpi < self.config.min_dpi:
            issues.append({"type": "LOW_RESOLUTION", "desc": f"Resolucion detectada: {dpi} DPI (Min: {self.config.min_dpi})"})
            if status != "QUALITY_BLOCKED":
                status = "QUALITY_EXCEPTION_REQUIRED" if dpi < 100 else "QUALITY_WARNING"
                
        if blur < self.config.min_blur_score:
            issues.append({"type": "HIGH_BLUR", "desc": f"El texto presenta un alto nivel de difuminacion (Blur: {blur})"})
            if status != "QUALITY_BLOCKED":
                status = "QUALITY_EXCEPTION_REQUIRED"
                
        if abs(rotation) > self.config.max_rotation_degrees:
            issues.append({"type": "ROTATION_DETECTED", "desc": f"Documento torcido ({rotation} grados)"})
            if status not in ["QUALITY_BLOCKED", "QUALITY_EXCEPTION_REQUIRED"]:
                status = "QUALITY_WARNING"
                
        if contrast < self.config.min_contrast_ratio:
            issues.append({"type": "LOW_CONTRAST", "desc": "Contraste insuficiente (Texto gris sobre fondo oscuro)"})
            if status not in ["QUALITY_BLOCKED", "QUALITY_EXCEPTION_REQUIRED"]:
                status = "QUALITY_WARNING"
                
        expected_ocr = "HIGH" if status == "QUALITY_GOOD" else "MEDIUM" if status == "QUALITY_WARNING" else "LOW"
        
        assessment = DocumentQualityAssessment(
            document_id=document_id,
            quality_status=status,
            dpi_estimate=dpi,
            rotation_detected=abs(rotation) > 0,
            blur_score=blur,
            ocr_expected_quality=expected_ocr,
            issues=issues
        )
        return assessment
