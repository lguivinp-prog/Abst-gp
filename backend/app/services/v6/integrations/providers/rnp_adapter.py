from typing import Dict, Any
from .base_provider import ExternalProviderInterface, ValidationResult
import os
import requests
import datetime

class RNPProvider(ExternalProviderInterface):
    def validate(self, identifier: str, fallback_evidence: Dict[str, Any] = None) -> ValidationResult:
        is_test = os.getenv("APP_ENV") == "test"

        if is_test:
            return ValidationResult(
                status="PASSED",
                source="RNP_API_MOCK",
                payload={"ruc": identifier, "registro": "VIGENTE", "capacidad": "1000000"}
            )

        url = f"https://www.rnp.gob.pe/constancia/rnp_constancia/default_Todos.asp?RUC={identifier}"
        headers = {
            "User-Agent": "Mozilla/5.0",
        }

        payload = {}
        status = "MANUAL_REQUIRED"
        source = "NO_DISPONIBLE_API"

        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                html = response.text
                if "captcha" in html.lower() or "grecaptcha" in html.lower():
                    payload = {"error": "Fuente oficial RNP exige resolución de CAPTCHA. Validación manual requerida."}
                elif identifier in html:
                    bienes = "PROVEEDOR DE BIENES" in html.upper()
                    servicios = "PROVEEDOR DE SERVICIOS" in html.upper()
                    status = "PASSED" if (bienes or servicios) else "WARNING"
                    source = "RNP_CONSTANCIA_PUBLICA"
                    payload = {
                        "ruc": identifier,
                        "bienes": bienes,
                        "servicios": servicios,
                        "registro": "VIGENTE" if (bienes or servicios) else "NO_VIGENTE",
                        "vigencia": "Datos extraidos de html publico"
                    }
                else:
                    payload = {"error": f"La respuesta no parece contener el RUC {identifier} o es una página genérica."}
            else:
                payload = {"error": f"RNP retornó código {response.status_code}."}
        except Exception as e:
            payload = {"error": f"Error de conexión RNP: {str(e)}"}

        if status != "PASSED" and fallback_evidence and "registro" in fallback_evidence:
            # Manual fallback provided
            status = "PASSED" if fallback_evidence["registro"] == "VIGENTE" else "WARNING"
            return ValidationResult(
                status=status,
                source="MANUAL_DOCUMENT",
                payload=fallback_evidence
            )

        return ValidationResult(
            status=status,
            source=source,
            payload=payload
        )
