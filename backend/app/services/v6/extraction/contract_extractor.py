import re
from typing import Dict, Any, List

def extract_requirements_from_text(text: str, source_document: str = "doc") -> Dict[str, Any]:
    # Mocking a deterministic local extraction of requirements
    requirements = []

    # Plazo de entrega
    plazo_match = re.search(r'(?i)plazo(?: de entrega)?(?: m[áa]ximo)?\s*:?\s*(\d+)\s*(d[íi]as|meses)', text)
    if plazo_match:
        requirements.append({
            "key": "PLAZO_ENTREGA",
            "description": "Plazo de entrega",
            "numeric_value": float(plazo_match.group(1)),
            "unit": plazo_match.group(2).lower(),
            "comparator": "MAX",
            "confidence": 0.9,
            "source_document_id": source_document,
            "source_page": 1,
            "source_quote": plazo_match.group(0),
            "extraction_method": "LOCAL_REGEX",
            "review_status": "PENDING",
            "is_manual_edit": False
        })

    # Garantía
    garantia_match = re.search(r'(?i)garant[íi]a(?: m[íi]nima)?\s*:?\s*(\d+)\s*(meses|a[ñn]os)', text)
    if garantia_match:
        requirements.append({
            "key": "GARANTIA",
            "description": "Garantía mínima",
            "numeric_value": float(garantia_match.group(1)),
            "unit": garantia_match.group(2).lower(),
            "comparator": "MIN",
            "confidence": 0.9,
            "source_document_id": source_document,
            "source_page": 1,
            "source_quote": garantia_match.group(0),
            "extraction_method": "LOCAL_REGEX",
            "review_status": "PENDING",
            "is_manual_edit": False
        })

    # Vida útil
    vida_match = re.search(r'(?i)vida [úu]til(?: m[íi]nima)?\s*:?\s*(\d+)\s*(a[ñn]os|meses)', text)
    if vida_match:
        requirements.append({
            "key": "VIDA_UTIL",
            "description": "Vida útil",
            "numeric_value": float(vida_match.group(1)),
            "unit": vida_match.group(2).lower(),
            "comparator": "MIN",
            "confidence": 0.9,
            "source_document_id": source_document,
            "source_page": 1,
            "source_quote": vida_match.group(0),
            "extraction_method": "LOCAL_REGEX",
            "review_status": "PENDING",
            "is_manual_edit": False
        })

    return {"requirements": requirements}

def extract_offer_terms_from_text(text: str, source_document: str = "doc") -> Dict[str, Any]:
    terms = []

    # Plazo ofertado
    plazo_match = re.search(r'(?i)plazo(?: ofertado| de entrega)?\s*:?\s*(\d+)\s*(d[íi]as|meses)', text)
    if plazo_match:
        terms.append({
            "key": "PLAZO_ENTREGA",
            "label": "Plazo ofertado",
            "value_text": plazo_match.group(0),
            "numeric_value": float(plazo_match.group(1)),
            "unit": plazo_match.group(2).lower(),
            "confidence": 0.9,
            "source_document_id": source_document,
            "source_page": 1,
            "source_quote": plazo_match.group(0),
            "extraction_method": "LOCAL_REGEX",
            "review_status": "PENDING",
            "is_manual_edit": False
        })

    # Garantía
    garantia_match = re.search(r'(?i)garant[íi]a(?: ofertada)?\s*:?\s*(\d+)\s*(meses|a[ñn]os)', text)
    if garantia_match:
        terms.append({
            "key": "GARANTIA",
            "label": "Garantía ofertada",
            "value_text": garantia_match.group(0),
            "numeric_value": float(garantia_match.group(1)),
            "unit": garantia_match.group(2).lower(),
            "confidence": 0.9,
            "source_document_id": source_document,
            "source_page": 1,
            "source_quote": garantia_match.group(0),
            "extraction_method": "LOCAL_REGEX",
            "review_status": "PENDING",
            "is_manual_edit": False
        })

    # Vida útil
    vida_match = re.search(r'(?i)vida [úu]til(?: ofertada)?\s*:?\s*(\d+)\s*(a[ñn]os|meses)', text)
    if vida_match:
        terms.append({
            "key": "VIDA_UTIL",
            "label": "Vida útil ofertada",
            "value_text": vida_match.group(0),
            "numeric_value": float(vida_match.group(1)),
            "unit": vida_match.group(2).lower(),
            "confidence": 0.9,
            "source_document_id": source_document,
            "source_page": 1,
            "source_quote": vida_match.group(0),
            "extraction_method": "LOCAL_REGEX",
            "review_status": "PENDING",
            "is_manual_edit": False
        })

    # Precio
    precio_match = re.search(r'(?i)precio(?: total)?\s*:?\s*(?:S/|s/|S/\.)\s*([\d,]+\.?\d*)', text)
    if precio_match:
        val = float(precio_match.group(1).replace(',', ''))
        terms.append({
            "key": "PRECIO_TOTAL",
            "label": "Precio total",
            "value_text": precio_match.group(0),
            "numeric_value": val,
            "unit": "PEN",
            "confidence": 0.9,
            "source_document_id": source_document,
            "source_page": 1,
            "source_quote": precio_match.group(0),
            "extraction_method": "LOCAL_REGEX",
            "review_status": "PENDING",
            "is_manual_edit": False
        })

    return {"terms": terms}
