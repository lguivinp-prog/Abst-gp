from typing import Dict, Any
from sqlalchemy.orm import Session
from .base_provider import ValidationResult
from app.models.v6.ciiu_catalog import CiiuCatalog
import hashlib
import json

class CIIUProvider:
    def validate(self, db: Session, sunat_ciiu_code: str, expected_description_keywords: str) -> ValidationResult:
        """
        Takes the CIIU code extracted from SUNAT and checks it against the INEI Catalog.
        Then checks if the description somewhat matches the expected object of the case.
        Returns certainty levels: HIGH, MEDIUM, LOW, UNKNOWN mapping to PASSED/WARNING/BLOCKED.
        """
        if not sunat_ciiu_code:
            return ValidationResult(
                status="MANUAL_REQUIRED",
                source="CIIU_MATCH",
                payload={"error": "Missing SUNAT CIIU code. Provide manual evidence."}
            )
            
        ciiu = db.query(CiiuCatalog).filter_by(codigo=sunat_ciiu_code, activo=True).first()
        if not ciiu:
            return ValidationResult(
                status="WARNING",
                source="CIIU_MATCH",
                payload={"codigo": sunat_ciiu_code, "certeza": "UNKNOWN", "msg": "Codigo no encontrado en catalogo local INEI"}
            )
            
        # Very naive deterministic match for the mock
        keywords = expected_description_keywords.lower().split()
        match_count = sum(1 for k in keywords if k in ciiu.descripcion.lower())
        
        if match_count > 0 or len(keywords) == 0:
            status = "PASSED"
            certeza = "HIGH"
        else:
            status = "WARNING"
            certeza = "LOW"
            
        return ValidationResult(
            status=status,
            source="CIIU_MATCH",
            payload={"codigo": ciiu.codigo, "descripcion": ciiu.descripcion, "certeza": certeza}
        )
