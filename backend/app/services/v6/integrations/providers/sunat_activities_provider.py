import os
import requests
import re
from typing import Dict, Any
from .base_provider import ExternalProviderInterface, ValidationResult

class SunatActivitiesProvider(ExternalProviderInterface):
    def validate(self, identifier: str, fallback_evidence: Dict[str, Any] = None) -> ValidationResult:
        if fallback_evidence and "actividades_economicas" in fallback_evidence:
            activities = []
            for idx, act in enumerate(fallback_evidence.get("actividades_economicas", [])):
                activities.append({
                    "tipo": act.get("tipo", "SECUNDARIA"),
                    "orden": idx + 1,
                    "codigo_reportado": None,
                    "descripcion_sunat": act.get("descripcion_sunat", ""),
                    "raw_source_value": act.get("descripcion_sunat", "")
                })
            return ValidationResult(
                status="PASSED" if activities else "MANUAL_REQUIRED",
                source="MIGO_API",
                payload={"activities_complete": True, "activities_count": len(activities), "actividades": activities}
            )

        token = os.getenv("MIGO_API_TOKEN")
        if not token:
            return ValidationResult(
                status="MANUAL_REQUIRED",
                source="MIGO_API",
                payload={"activities_complete": False, "activities_count": 0, "error": "Token MIGO no configurado."}
            )

        url = f"https://api.migo.pe/api/v2/ruc/{identifier}/sunat"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json"
        }

        try:
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code == 200:
                data = response.json()

                if str(data.get("ruc", "")) != identifier:
                    return ValidationResult(
                        status="REVIEW_REQUIRED",
                        source="MIGO_API",
                        payload={"error": "RUC no coincide con la consulta.", "activities_complete": False, "activities_count": 0}
                    )

                actividades = data.get("actividades_economicas", [])

                activities = []
                for idx, act_str in enumerate(actividades):
                    tipo = "PRINCIPAL" if idx == 0 else "SECUNDARIA"

                    # Try to extract code and description
                    match = re.match(r'^(?:Principal|Secundaria\s*\d*)\s*-\s*(\d{4})\s*-\s*(.*)', act_str, flags=re.IGNORECASE)
                    if match:
                        codigo_reportado = match.group(1)
                        descripcion_sunat = match.group(2).strip()
                    else:
                        codigo_reportado = None
                        descripcion_sunat = re.sub(r'^(?:Principal|Secundaria\s*\d*)\s*-\s*', '', act_str, flags=re.IGNORECASE).strip()

                    activities.append({
                        "tipo": tipo,
                        "orden": idx + 1,
                        "codigo_reportado": codigo_reportado,
                        "descripcion_sunat": descripcion_sunat,
                        "raw_source_value": act_str
                    })

                status = "PASSED" if activities else "MANUAL_REQUIRED"

                payload = {
                    "activities_complete": len(activities) > 0,
                    "activities_count": len(activities),
                    "activities": activities,
                    "identity_verified": data.get("estado_del_contribuyente", "") == "ACTIVO"
                }

                return ValidationResult(status=status, source="MIGO_API", payload=payload)
            else:
                return ValidationResult(
                    status="MANUAL_REQUIRED",
                    source="MIGO_API",
                    payload={"activities_complete": False, "activities_count": 0, "error": f"API Error {response.status_code}"}
                )
        except Exception as e:
            return ValidationResult(
                status="MANUAL_REQUIRED",
                source="MIGO_API",
                payload={"activities_complete": False, "activities_count": 0, "error": str(e)}
            )
