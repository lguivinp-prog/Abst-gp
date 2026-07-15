import re
from typing import Dict, Any

def extract_products_basic(text: str) -> Dict[str, Any]:
    """
    Extracción heurística básica de producto o servicio principal.
    (Para extracción avanzada en tablas, se usaría table_extractor.py)
    """
    result = {
        "description": {"value": None, "confidence": 0.0, "source": "keywords"},
        "total_price": {"value": None, "confidence": 0.0, "source": "regex"},
        "currency": {"value": "PEN", "confidence": 0.5, "source": "default"}
    }
    
    # Extraer Total (S/, $, USD)
    total_match = re.search(r'(?i)(total|importe|monto).*?(S/|S/\.|USD|\$)\s*([\d\.,]+)', text)
    if total_match:
        currency = total_match.group(2).upper()
        if "USD" in currency or "$" in currency:
            result["currency"]["value"] = "USD"
        else:
            result["currency"]["value"] = "PEN"
            
        amount_str = total_match.group(3).replace(',', '').rstrip('.')
        try:
            result["total_price"]["value"] = float(amount_str)
            result["total_price"]["confidence"] = 0.85
        except ValueError:
            pass

    # Extraer descripción (basado en prefijos comunes)
    desc_match = re.search(r'(?i)(descripci[oó]n|concepto)\s*:?\s*([^\n]{5,100})', text)
    if desc_match:
        result["description"]["value"] = desc_match.group(2).strip()
        result["description"]["confidence"] = 0.7

    return result
