import os
from typing import Dict, Any
import fitz

from .supplier_extractor import extract_supplier_info
from .product_extractor import extract_products_basic
from .condition_extractor import extract_conditions
from .table_extractor import extract_tables_from_pdf

def parse_quotation_pdf(file_path: str) -> Dict[str, Any]:
    """
    Orquesta la extracción de datos de una cotización.
    """
    text_content = ""
    try:
        doc = fitz.open(file_path)
        for page in doc:
            text_content += page.get_text() + "\n"
        doc.close()
    except Exception as e:
        return {"error": str(e)}

    # Extracción de campos
    supplier_info = extract_supplier_info(text_content)
    product_info = extract_products_basic(text_content)
    condition_info = extract_conditions(text_content)
    
    # Extraer tablas si es posible
    tables = extract_tables_from_pdf(file_path)
    
    # Combinar resultados
    result = {
        "text_raw": text_content,
        "supplier": supplier_info,
        "product": product_info,
        "conditions": condition_info,
        "tables": tables,
        "global_confidence": 0.0
    }
    
    # Calcular confianza global simple
    confidences = [
        supplier_info["supplier_ruc"]["confidence"],
        product_info["total_price"]["confidence"],
        condition_info["payment_condition"]["confidence"]
    ]
    result["global_confidence"] = sum(confidences) / len(confidences) if confidences else 0.0
    
    return result
