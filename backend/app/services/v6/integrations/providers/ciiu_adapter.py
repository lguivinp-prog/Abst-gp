from typing import Dict, Any, List
from sqlalchemy.orm import Session
from .base_provider import ValidationResult
import datetime

class CIIUProvider:
    def validate(self, db: Session, sunat_ciiu: List[str], expected_keywords: str) -> ValidationResult:
        if not sunat_ciiu:
            return ValidationResult(
                status="MANUAL_REQUIRED",
                source="NO_DISPONIBLE",
                payload={"error": "No fue posible obtener la actividad económica desde SUNAT."}
            )
            
        return ValidationResult(
            status="PASSED",
            source="CIIU_DERIVED",
            payload={"ciiu": sunat_ciiu, "match_keywords": expected_keywords}
        )
