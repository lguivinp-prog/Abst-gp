from typing import Dict, Any
from .base_provider import ExternalProviderInterface, ValidationResult
import os

class FUPProvider(ExternalProviderInterface):
    def validate(self, identifier: str, fallback_evidence: Dict[str, Any] = None) -> ValidationResult:
        api_key = os.getenv("FUP_API_KEY")
        
        if api_key:
            # Simulating an API call that checks sanctions
            return ValidationResult(
                status="PASSED",
                source="FUP_API",
                payload={"ruc": identifier, "sancionado": False, "alertas": []}
            )
            
        if fallback_evidence and "sancionado" in fallback_evidence:
            status = "BLOCKED" if fallback_evidence["sancionado"] else "PASSED"
            return ValidationResult(
                status=status,
                source="MANUAL_DOCUMENT",
                payload=fallback_evidence
            )
            
        return ValidationResult(
            status="MANUAL_REQUIRED",
            source="NO_DISPONIBLE_API",
            payload={"error": "API Key missing. FUP sanction check is mandatory."}
        )
