from .interfaces import SUNATProviderInterface, ProviderResult
from datetime import datetime, timezone
import hashlib
import json

class SUNATMockProvider(SUNATProviderInterface):
    def validate(self, identifier: str) -> ProviderResult:
        # Mocking determinist logic
        status = "PASSED"
        if identifier.startswith("10"):
            status = "WARNING"
        elif identifier.startswith("00"):
            status = "BLOCKED"
            
        payload = {
            "razon_social": "MOCK ENTERPRISE S.A.C",
            "estado": "ACTIVO",
            "condicion": "HABIDO",
            "actividades_economicas": ["6201", "6202"]
        }
        
        payload_str = json.dumps(payload, sort_keys=True)
        hash_val = hashlib.sha256(payload_str.encode()).hexdigest()
        
        return ProviderResult(
            result="Validacion SUNAT completada",
            status=status,
            source="SUNAT",
            timestamp=datetime.now(timezone.utc).isoformat(),
            payload=payload,
            hash_val=hash_val
        )
