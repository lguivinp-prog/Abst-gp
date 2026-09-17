from typing import Dict, Any
from .base_provider import ExternalProviderInterface, ValidationResult
import os
import requests
import datetime
import certifi

class FUPProvider(ExternalProviderInterface):
    def validate(self, identifier: str, fallback_evidence: Dict[str, Any] = None) -> ValidationResult:
        is_test = os.getenv("APP_ENV") == "test"

        if is_test:
            return ValidationResult(
                status="PASSED",
                source="FUP_API_MOCK",
                payload={"ruc": identifier, "impedimentos": False, "sanciones": False}
            )

        url = f"https://apps.osce.gob.pe/perfilprov-api/api/proveedor/busqueda?numeroRuc={identifier}&tipoDocumento=RUC"
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json"
        }

        payload = {}
        status = "MANUAL_REQUIRED"
        source = "NO_DISPONIBLE_API"

        try:
            response = requests.get(url, headers=headers, timeout=15, verify=certifi.where())
            if response.status_code == 200:
                data = response.json()
                # Parse OSCE response if valid
                if data and isinstance(data, list) and len(data) > 0 and data[0].get("numeroDocumento") == identifier:
                    status = "PASSED"
                    source = "FUP_OSCE_API"

                    prov_data = data[0]
                    # We would fetch detailed data from `/api/proveedor/{id}` if we had it, but from list:
                    payload = {
                        "ruc": identifier,
                        "razon_social": prov_data.get("razonSocial"),
                        "tipo_documento": prov_data.get("tipoDocumento"),
                        "estado": prov_data.get("estado"),
                        "impedimentos": prov_data.get("impedimentos", False),
                        "sanciones": prov_data.get("sanciones", False),
                        "info_msg": "Datos extraídos de FUP oficial"
                    }
                else:
                    payload = {"error": "FUP API retornó respuesta vacía o no coincidente. Validación manual requerida."}
            elif response.status_code == 403 or response.status_code == 429:
                payload = {"error": f"FUP WAF bloqueó la petición (código {response.status_code}). Validación manual requerida."}
            else:
                payload = {"error": f"FUP retornó código {response.status_code}."}
        except requests.exceptions.SSLError as e:
            payload = {"error": f"Error de conexión FUP: TLS verification failed", "technical_detail": str(e)}
        except ValueError:
            payload = {"error": "FUP no devolvió JSON válido. Validación manual requerida."}
        except Exception as e:
            payload = {"error": f"Error de conexión FUP", "technical_detail": str(e)}

        if status != "PASSED" and fallback_evidence and "impedimentos" in fallback_evidence:
            status = "WARNING" if fallback_evidence["impedimentos"] else "PASSED"
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
