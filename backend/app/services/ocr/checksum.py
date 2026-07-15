import json
import hashlib
from typing import Dict, Any

def canonicalize_structured_document(doc_dict: Dict[str, Any]) -> bytes:
    """
    Serializes a dictionary (StructuredDocument or similar) canonically.
    - Excludes 'checksum' field if present
    - Sorts keys
    - UTF-8 representation
    - ensure_ascii=False
    - No leading/trailing whitespaces in separators (indent=2 is used for readability, but separators=(',', ': ') or just indentation)
    We stick to json.dumps with sort_keys=True, indent=2, ensure_ascii=False for backwards compatibility with AtomicPersistence.
    """
    # Create a copy to avoid mutating the original
    clean_dict = dict(doc_dict)
    
    if "checksum" in clean_dict:
        del clean_dict["checksum"]
        
    return json.dumps(clean_dict, ensure_ascii=False, indent=2, sort_keys=True).encode('utf-8')

def calculate_structured_document_checksum(doc_dict: Dict[str, Any]) -> str:
    """
    Calculates the SHA-256 checksum of the canonically serialized document.
    """
    canonical_bytes = canonicalize_structured_document(doc_dict)
    return hashlib.sha256(canonical_bytes).hexdigest()

def calculate_baseline_hash(sections: list, html: str, docx_path: str) -> str:
    """
    Calculates a combined baseline hash for V1 results to ensure immutability before V2 shadow.
    """
    baseline = {
        "sections_count": len(sections),
        "sections": [{"id": s.id, "text": s.current_text, "confidence": s.confidence_score} for s in sections],
        "has_html": bool(html),
        "has_docx": bool(docx_path)
    }
    canonical_bytes = json.dumps(baseline, ensure_ascii=False, sort_keys=True).encode('utf-8')
    return hashlib.sha256(canonical_bytes).hexdigest()
