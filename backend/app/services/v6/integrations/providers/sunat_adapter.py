from typing import Dict, Any
from .base_provider import ExternalProviderInterface, ValidationResult
import os
import requests
from typing import Dict, Any
from .base_provider import ExternalProviderInterface, ValidationResult

class SUNATProvider(ExternalProviderInterface):
    def validate(self, identifier: str, fallback_evidence: Dict[str, Any] = None) -> ValidationResult:
        if fallback_evidence:
            estado = fallback_evidence.get("estado", "")
            condicion = fallback_evidence.get("condicion", "")
            status = "PASSED" if estado == "ACTIVO" and condicion == "HABIDO" else "WARNING"
            return ValidationResult(
                status=status,
                source="DECOLECTA",
                payload={"estado": estado, "condicion": condicion}
            )

        token = os.getenv("DECOLECTA_API_TOKEN")
        if not token:
            return ValidationResult(
                status="MANUAL_REQUIRED",
                source="NO_DISPONIBLE_API",
                payload={"error": "Token de Decolecta no configurado."}
            )

        url = f"https://api.decolecta.com/v1/sunat/ruc/full"
        headers = {"Authorization": f"Bearer {token}"}
        params = {"numero": identifier}

        try:
            resp = requests.get(url, params=params, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                estado = data.get("estado", "")
                condicion = data.get("condicion", "")
                status = "PASSED" if estado == "ACTIVO" and condicion == "HABIDO" else "WARNING"
                payload = {
                    "ruc": identifier,
                    "razon_social": data.get("razon_social", ""),
                    "estado": estado,
                    "condicion": condicion,
                    "actividad_reportada_decolecta": data.get("actividad_economica", ""),
                    "actividad_economica": data.get("actividad_economica", ""), # Legacy alias
                    "domicilio": data.get("direccion", ""),
                    "integration_provider": "DECOLECTA"
                }
                return ValidationResult(
                    status=status,
                    source="SUNAT_DECOLECTA",
                    payload=payload
                )
            else:
                return ValidationResult(
                    status="MANUAL_REQUIRED",
                    source="SUNAT_DECOLECTA",
                    payload={
                        "error": "Error al consultar API Decolecta.",
                        "technical_detail": f"Status: {resp.status_code}"
                    }
                )
        except Exception as e:
            return ValidationResult(
                status="MANUAL_REQUIRED",
                source="SUNAT_DECOLECTA",
                payload={
                    "error": "Error de conexión con Decolecta.",
                    "technical_detail": str(e)
                }
            )
