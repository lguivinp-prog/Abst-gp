import json
import hashlib
from decimal import Decimal
from datetime import datetime, date, timezone
from typing import Any, Union, Dict, List

class CanonicalSerializer:
    """
    Serializador canónico determinista versionado (ABST-CANONICAL-V1) para snapshots técnicos P13.
    Garantiza:
    - Orden determinista estricto de claves recursivo (sort_keys=True).
    - Separadores compactos sin espacios variables (separators=(',', ':')).
    - Preservación íntegra de Unicode (ensure_ascii=False).
    - Conversión de Decimal a string numérico exacto sin notación científica ni imprecisión float.
    - Fechas y datetimes convertidos a UTC (astimezone(timezone.utc)) con formato ISO 8601 terminado en 'Z'.
    - Preservación explícita de valores null.
    - Invarianza de hash frente a serialización y persistencia en columnas JSONB.
    - Cálculo de hash SHA-256 sobre los bytes UTF-8 exactos resultantes.
    """

    VERSION = "ABST-CANONICAL-V1"

    @classmethod
    def _normalize_obj(cls, obj: Any) -> Any:
        if obj is None:
            return None
        if isinstance(obj, Decimal):
            # Normalización determinista de Decimal sin notación científica
            return format(obj, 'f')
        if isinstance(obj, (datetime, date)):
            if isinstance(obj, datetime):
                # Conversión explícita y forzada a UTC independiente del TZ del entorno operativo
                if obj.tzinfo is not None:
                    utc_dt = obj.astimezone(timezone.utc)
                else:
                    utc_dt = obj.replace(tzinfo=timezone.utc)
                return utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            return obj.isoformat()
        if isinstance(obj, dict):
            # Ordenar claves recursivamente de forma lexicográfica
            return {str(k): cls._normalize_obj(v) for k, v in sorted(obj.items(), key=lambda item: str(item[0]))}
        if isinstance(obj, set):
            normalized_items = [cls._normalize_obj(item) for item in obj]
            return sorted(normalized_items, key=lambda x: json.dumps(x, sort_keys=True, ensure_ascii=False, default=str))
        if isinstance(obj, (list, tuple)):
            return [cls._normalize_obj(item) for item in obj]
        return obj

    @classmethod
    def serialize_to_bytes(cls, data: Any) -> bytes:
        normalized = cls._normalize_obj(data)
        serialized_str = json.dumps(
            normalized,
            sort_keys=True,
            separators=(',', ':'),
            ensure_ascii=False
        )
        return serialized_str.encode('utf-8')

    @classmethod
    def calculate_hash(cls, data_or_bytes: Union[Any, bytes]) -> str:
        if isinstance(data_or_bytes, bytes):
            raw_bytes = data_or_bytes
        else:
            raw_bytes = cls.serialize_to_bytes(data_or_bytes)
        return hashlib.sha256(raw_bytes).hexdigest()

    @classmethod
    def verify_hash(cls, data_or_bytes: Union[Any, bytes], expected_hash: str) -> bool:
        if not expected_hash:
            return False
        calculated = cls.calculate_hash(data_or_bytes)
        return calculated.lower() == expected_hash.strip().lower()
