from typing import Dict, List, Any
from .comparison_status import ComparisonStatus
from .precedence_rules import PRECEDENCE_RULES

def compare_field(field_name: str, req_val: str, quot_val: str) -> Dict[str, Any]:
    """
    Compara un solo campo y aplica reglas de prevalencia.
    """
    req_val = req_val.strip() if req_val else None
    quot_val = quot_val.strip() if quot_val else None
    
    result = {
        "field_name": field_name,
        "requirement_value": req_val,
        "quotation_value": quot_val,
        "final_value": None,
        "status": None
    }
    
    if not req_val and not quot_val:
        result["status"] = ComparisonStatus.REVISION_MANUAL.value
        return result
        
    if not req_val and quot_val:
        result["status"] = ComparisonStatus.NO_DETECTADO_REQUERIMIENTO.value
        result["final_value"] = quot_val
        return result
        
    if req_val and not quot_val:
        result["status"] = ComparisonStatus.NO_DETECTADO_COTIZACION.value
        result["final_value"] = req_val
        return result
        
    # Ambos existen
    if req_val.lower() == quot_val.lower():
        result["status"] = ComparisonStatus.COINCIDE.value
        result["final_value"] = req_val
        return result
        
    # Hay conflicto, aplicar precedencia
    precedence = PRECEDENCE_RULES.get(field_name, "requirement")
    if precedence == "quotation":
        result["status"] = ComparisonStatus.REEMPLAZADO_POR_COTIZACION.value
        result["final_value"] = quot_val
    else:
        result["status"] = ComparisonStatus.REVISION_MANUAL.value # O podría ser REEMPLAZADO_POR_REQ
        result["final_value"] = req_val
        
    return result

def run_comparison(requirement_data: Dict[str, str], quotation_data: Dict[str, str]) -> List[Dict[str, Any]]:
    """
    Toma los datos extraídos del requerimiento y la cotización y devuelve
    la matriz de comparación.
    """
    fields_to_compare = [
        "payment_condition",
        "delivery_term",
        "execution_term",
        "warranty_term",
        "warranty_conditions"
    ]
    
    results = []
    for field in fields_to_compare:
        req_val = requirement_data.get(field)
        quot_val = quotation_data.get(field)
        
        comp_result = compare_field(field, req_val, quot_val)
        results.append(comp_result)
        
    return results
