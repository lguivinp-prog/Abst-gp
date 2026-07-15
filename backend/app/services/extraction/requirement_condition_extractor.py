import re
from typing import Dict, List, Any

def extract_requirement_conditions(sections: List[Any]) -> Dict[str, str]:
    """
    Extrae condiciones específicas de las secciones del requerimiento.
    Acepta una lista de objetos ParsedSection o diccionarios similares.
    """
    result = {
        "payment_condition": None,
        "delivery_term": None,
        "execution_term": None,
        "warranty_term": None,
        "warranty_conditions": None
    }
    
    # Patrones para buscar dentro del texto
    patterns = {
        "payment_condition": [r'(?i)(forma|condici[oó]n)\s+de\s+pago.*?([\w\s\d%]+(?:d[ií]as|calendario|armadas?|entregas?|partes?|mensual|suscripci[oó]n|conformidad))'],
        "delivery_term": [r'(?i)plazo\s+de\s+entrega.*?(\d+\s+d[ií]as)'],
        "execution_term": [r'(?i)plazo\s+de\s+ejecuci[oó]n.*?(\d+\s+d[ií]as)'],
        "warranty_term": [r'(?i)garant[ií]a\s+comercial.*?(\d+\s+(?:meses|a[nñ]os?|d[ií]as))'],
        "warranty_conditions": [r'(?i)condiciones\s+de\s+garant[ií]a.*?([^\n]+)']
    }
    
    for section in sections:
        text_to_search = getattr(section, 'current_text', None) or getattr(section, 'original_text', '') or ""
        
        for key, pat_list in patterns.items():
            if result[key] is not None:
                continue
            
            for pat in pat_list:
                match = re.search(pat, text_to_search)
                if match:
                    if match.groups():
                        val = match.group(match.lastindex)
                        result[key] = val.strip()
                        break
    
    return result
