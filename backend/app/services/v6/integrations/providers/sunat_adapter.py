from typing import Dict, Any
from .base_provider import ExternalProviderInterface, ValidationResult
import os

class SUNATProvider(ExternalProviderInterface):
    def validate(self, identifier: str, fallback_evidence: Dict[str, Any] = None) -> ValidationResult:
        is_test = os.getenv("APP_ENV") == "test"
        
        if is_test:
            return ValidationResult(
                status="PASSED",
                source="SUNAT_API_MOCK",
                payload={"ruc": identifier, "estado": "ACTIVO", "condicion": "HABIDO"}
            )
            
        if fallback_evidence and "estado" in fallback_evidence:
            # Manual fallback provided
            status = "PASSED" if fallback_evidence["estado"] == "ACTIVO" else "WARNING"
            return ValidationResult(
                status=status,
                source="MANUAL_DOCUMENT",
                payload=fallback_evidence
            )
            
        return ValidationResult(
            status="MANUAL_REQUIRED",
            source="NO_DISPONIBLE_API",
            payload={"error": "API Key missing and no fallback evidence provided."}
        )
