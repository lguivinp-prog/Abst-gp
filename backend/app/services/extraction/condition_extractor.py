import re
from typing import Dict, Any

def extract_conditions(text: str) -> Dict[str, Any]:
    """
    Extrae condiciones comerciales y contractuales de una cotización.
    """
    result = {
        "payment_condition": {"value": None, "confidence": 0.0, "source": "keywords", "needs_review": True},
        "delivery_term": {"value": None, "confidence": 0.0, "source": "keywords", "needs_review": True},
        "execution_term": {"value": None, "confidence": 0.0, "source": "keywords", "needs_review": True},
        "warranty_term": {"value": None, "confidence": 0.0, "source": "keywords", "needs_review": True},
    }
    
    # 1. Condición de pago
    payment_match = re.search(r'(?i)(condici[oó]n|forma)\s+de\s+pago\s*:?\s*([^\n]{5,50})', text)
    if payment_match:
        result["payment_condition"]["value"] = payment_match.group(2).strip()
        result["payment_condition"]["confidence"] = 0.9
        result["payment_condition"]["needs_review"] = False
        
    # 2. Plazo de entrega (Bienes)
    delivery_match = re.search(r'(?i)(tiempo|plazo)\s+de\s+entrega\s*:?\s*([^\n]{5,50})', text)
    if delivery_match:
        result["delivery_term"]["value"] = delivery_match.group(2).strip()
        result["delivery_term"]["confidence"] = 0.9
        result["delivery_term"]["needs_review"] = False
        
    # 3. Plazo de ejecución (Servicios)
    execution_match = re.search(r'(?i)plazo\s+de\s+ejecuci[oó]n\s*:?\s*([^\n]{5,50})', text)
    if execution_match:
        result["execution_term"]["value"] = execution_match.group(1).strip()
        result["execution_term"]["confidence"] = 0.9
        result["execution_term"]["needs_review"] = False
        
    # 4. Garantía
    warranty_match = re.search(r'(?i)garant[ií]a\s*:?\s*([^\n]{2,30})', text)
    if warranty_match:
        result["warranty_term"]["value"] = warranty_match.group(1).strip()
        result["warranty_term"]["confidence"] = 0.9
        result["warranty_term"]["needs_review"] = False

    return result
