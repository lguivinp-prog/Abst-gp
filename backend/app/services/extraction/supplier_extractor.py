import re
from typing import Dict, Any, Tuple

def extract_supplier_info(text: str) -> Dict[str, Any]:
    """
    Extrae información del proveedor de una cotización con un nivel de confianza.
    """
    result = {
        "supplier_ruc": {"value": None, "confidence": 0.0, "source": "regex", "needs_review": True},
        "supplier_business_name": {"value": None, "confidence": 0.0, "source": "keywords", "needs_review": True},
        "supplier_email": {"value": None, "confidence": 0.0, "source": "regex", "needs_review": False},
        "supplier_phone": {"value": None, "confidence": 0.0, "source": "regex", "needs_review": False},
    }
    
    ruc_match = re.search(r'\b(10|15|17|20)\d{9}\b', text)
    if ruc_match:
        result["supplier_ruc"]["value"] = ruc_match.group(0)
        result["supplier_ruc"]["confidence"] = 1.0 # RUC es muy estricto
        result["supplier_ruc"]["needs_review"] = False
    
    # 2. Extraer Email
    email_match = re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', text)
    if email_match:
        result["supplier_email"]["value"] = email_match.group(0)
        result["supplier_email"]["confidence"] = 0.95
        
    # 3. Extraer Teléfono (formatos peruanos básicos: 9 dígitos, fijos con código)
    phone_match = re.search(r'\b(9\d{8}|0[1-8]{1,2}-\d{6,7})\b', text)
    if phone_match:
        result["supplier_phone"]["value"] = phone_match.group(0)
        result["supplier_phone"]["confidence"] = 0.8
        
    # 4. Razón Social (Heurística simple basada en palabras clave)
    business_match = re.search(r'(?i)(raz[oó]n social|señor\(?e?s?\)?|cliente|empresa)\s*:?\s*([A-Za-z0-9\s\.\,\&]{5,50})(?=\n|$)', text)
    if business_match:
        result["supplier_business_name"]["value"] = business_match.group(2).strip()
        result["supplier_business_name"]["confidence"] = 0.85
        result["supplier_business_name"]["needs_review"] = False

    return result
