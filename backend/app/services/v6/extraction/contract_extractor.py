import re
from typing import Dict, Any, List

def is_template_instruction(text: str) -> bool:
    # Normalize text for checking
    normalized = text.strip()
    # Remove common bullet points like U+F0B7, hyphen, etc at the start
    normalized = re.sub(r'^[\uf0b7\-\u2022\s]+', '', normalized)
    normalized = " ".join(normalized.split()).casefold()

    instruction_patterns = [
        r'\[\s*en caso corresponda\b.*?(?:\]|$)',
        r'\[\s*de preverse.*?(?:\]|$)',
        r'^condiciones de la garant[ií]a\s*:\s*indicar',
        r'^per[ií]odo de garant[ií]a\s*:\s*por tiempo',
        r'^inicio del c[oó]mputo.*?a partir de',
        r'^\d+\.\d+\s+garant[ií]a comercial$',
        # Extended patterns
        r'\[.*?\]', # Any block entirely in brackets or part of a bracket block (if handled properly line by line, but multiline needs special care. For now this catches single line blocks. We will handle multiline state in extractor).
        r'^\(de acuerdo a.*?\)$',
        r'^\(de ser el caso\)$',
        r'^\(se debe indicar.*?\)$',
        r'^13\.2\s+otras penalidades\s*\(de corresponder\)$'
    ]
    for pattern in instruction_patterns:
        if re.search(pattern, normalized):
            return True
    return False

def extract_requirements_from_text(text: str, source_document: str = "doc") -> Dict[str, Any]:
    # Mocking a deterministic local extraction of requirements
    requirements = []

    # Plazo de entrega
    plazo_match = re.search(r'(?i)plazo(?: de entrega)?(?: m[aá]ximo)?\s*:?\s*(\d+)\s*(d[ií]as|meses)', text)
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
    garantia_match = re.search(r'(?i)garant[ií]a(?: m[ií]nima)?\s*:?\s*(\d+)\s*(meses|a[nñ]os)', text)
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
    vida_match = re.search(r'(?i)vida [uú]til(?: m[ií]nima)?\s*:?\s*(\d+)\s*(a[nñ]os|meses)', text)
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
    plazo_match = re.search(r'(?i)plazo(?: ofertado| de entrega)?\s*:?\s*(\d+)\s*(d[ií]as|meses)', text)
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
    garantia_match = re.search(r'(?i)garant[ií]a(?: ofertada)?\s*:?\s*(\d+)\s*(meses|a[nñ]os)', text)
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
    vida_match = re.search(r'(?i)vida [uú]til(?: ofertada)?\s*:?\s*(\d+)\s*(a[nñ]os|meses)', text)
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
