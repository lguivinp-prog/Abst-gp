import re
import unicodedata
from typing import Dict, Any, List, Optional, Tuple
from app.models.v6.case_requirement_matrix import RequirementCategory, RequirementPhase

def normalize_for_matching(text: str) -> str:
    """Robust Unicode normalization to ASCII for matching without destroying original text."""
    # Normalize to NFKD, keep only non-combining characters (strip accents)
    normalized = unicodedata.normalize('NFKD', text)
    ascii_text = ''.join([c for c in normalized if not unicodedata.combining(c)])
    # Casefold and collapse whitespace
    return " ".join(ascii_text.casefold().split())

def is_context(normalized: str, original: str) -> bool:
    patterns = [
        r'finalidad publica',
        r'objetivo de(?: la)? contratacion',
        r'antecedentes',
        r'introduccion',
    ]
    for pattern in patterns:
        if re.search(pattern, normalized):
            return True
            
    # Semantic rules for institutional context
    context_phrases = [
        r'en el marco de sus funciones',
        r'requiere contar con',
        r'para desarrollar',
        r'con la finalidad',
        r'fortalecer la capacidad'
    ]
    matches = sum(1 for phrase in context_phrases if re.search(phrase, normalized))
    if matches >= 2 and not is_item_specification_keyword(normalized):
        return True

    return False

def is_template_instruction(normalized: str) -> bool:
    instruction_patterns = [
        r'\[\s*en caso corresponda\b.*?(?:\]|$)',
        r'\[\s*de preverse.*?(?:\]|$)',
        r'^condiciones de la garantia\s*:\s*indicar',
        r'^periodo de garantia\s*:\s*por tiempo',
        r'^inicio del computo.*?a partir de',
        r'^\d+\.\d+\s+garantia comercial$',
        r'\[.*?\]', 
        r'^\(de acuerdo a.*?\)$',
        r'^\(de ser el caso\)$',
        r'^\(se debe indicar.*?\)$',
        r'^13\.2\s+otras penalidades\s*\(de corresponder\)$'
    ]
    for pattern in instruction_patterns:
        if re.search(pattern, normalized):
            return True
    return False

def is_selection_requirement(normalized: str) -> bool:
    patterns = [
        r'experiencia del postor',
        r'habilitacion',
        r'capacidad legal',
        r'capacidad tecnica y profesional',
        r'documentacion de presentacion obligatoria',
    ]
    for pattern in patterns:
        if re.search(pattern, normalized):
            return True
    return False

def is_item_specification_keyword(normalized: str) -> bool:
    keywords = [
        r'^caracteristicas', r'^color', r'^material', r'^materia prima',
        r'^dimensiones', r'^tipo', r'^presentacion', r'^olor',
        r'^resistencia', r'^mango', r'^virola', r'^medidas', r'^acabado',
        r'^volumen', r'^largo', r'^piezas', r'^empaque', r'^distancia'
    ]
    for pattern in keywords:
        if re.search(pattern, normalized):
            return True
    return False

def is_general_obligation(normalized: str) -> bool:
    patterns = [
        r'alcance de la garantia',
        r'condiciones de garantia',
        r'cobertura de garantia',
        r'defectos de fabricacion',
        r'reposicion por garantia'
    ]
    for pattern in patterns:
        if re.search(pattern, normalized):
            return True
    return False

def extract_distinctive_tokens(description: str) -> Tuple[str, set]:
    if not description:
        return "", set()
    normalized = normalize_for_matching(description)
    tokens = re.findall(r'\b[a-z0-9]+\b', normalized)
    stopwords = {
        'de', 'con', 'para', 'tipo', 'unidad', 'color', 'y', 'o', 'en', 'el', 'la', 'los', 'las',
        'por', 'su', 'sus', 'un', 'una', 'uso', 'medida', 'talla', 'forma', 'peso'
    }
    valid_tokens = [t for t in tokens if t not in stopwords]
    primary_token = valid_tokens[0] if valid_tokens else ""
    return primary_token, set(valid_tokens)

def match_procurement_item(normalized: str, procurement_items: List[Any], specifications: List[Any]) -> Optional[int]:
    """
    Tries to unambiguously match a requirement to a specific procurement item using scoring.
    Returns procurement_item_id if unambiguous, None otherwise.
    """
    scores = {}
    
    # 1. Strong priority matching based on distinctive tokens from item description
    for item in procurement_items:
        primary_token, tokens = extract_distinctive_tokens(item.description)
        score = 0
        if primary_token:
            match = re.search(rf'\b{primary_token}\b', normalized)
            if match:
                # Primary token gives a huge boost, more if closer to the start of the requirement
                score += 100 - min(match.start(), 50)
                
        for token in tokens:
            if token != primary_token:
                match = re.search(rf'\b{token}\b', normalized)
                if match:
                    score += 30 - min(match.start(), 20)
                    
        if score > 0:
            scores[item.id] = scores.get(item.id, 0) + score
            
    # 2. Add evidence from exact match of spec value
    for spec in specifications:
        spec_val = normalize_for_matching(str(spec.value))
        spec_name = normalize_for_matching(str(spec.name))
        
        # Generic fields do not assign an item by themselves
        generic_names = {'tipo', 'color', 'material', 'presentacion', 'volumen', 'caracteristicas', 'olor', 'mango', 'virola'}
        
        has_name = bool(re.search(rf'\b{re.escape(spec_name)}\b', normalized)) if spec_name else False
        has_val = bool(re.search(rf'\b{re.escape(spec_val)}\b', normalized)) if spec_val else False
        
        if spec_name in generic_names:
            if spec_val and has_val:
                scores[spec.procurement_item_id] = scores.get(spec.procurement_item_id, 0) + 5
        else:
            if has_name and has_val:
                scores[spec.procurement_item_id] = scores.get(spec.procurement_item_id, 0) + 20

    if not scores:
        return None
        
    # Sort items by score descending
    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    best_item_id, best_score = sorted_scores[0]
    
    # C. Si varios ítems tienen puntuación equivalente o no existe margen suficiente: return None
    if len(sorted_scores) > 1:
        second_best_id, second_best_score = sorted_scores[1]
        # Require a margin of at least 5 points to consider unambiguous
        if (best_score - second_best_score) < 5:
            return None
            
    # Only return if we have a solid score
    if best_score >= 5:
        return best_item_id
        
    return None

def determine_phase_and_flow(category: str, normalized: str) -> Tuple[str, bool]:
    if category == RequirementCategory.CONTEXT:
        return RequirementPhase.CONTEXT, False
    elif category == RequirementCategory.SELECTION_REQUIREMENT:
        return RequirementPhase.SELECTION, False
    elif category == RequirementCategory.ITEM_SPECIFICATION:
        return RequirementPhase.EVALUATION, True
    elif category == RequirementCategory.CONTRACTUAL_TERM:
        return RequirementPhase.CONTRACT_EXECUTION, True
    elif category == RequirementCategory.GENERAL_OBLIGATION:
        eval_keywords = ['acreditar', 'presentar', 'oferta', 'postor', 'propuesta']
        if any(k in normalized for k in eval_keywords):
            return RequirementPhase.EVALUATION, True
        return RequirementPhase.CONTRACT_EXECUTION, True
    
    return RequirementPhase.CONTRACT_EXECUTION, True

def classify_requirement(
    candidate_text: str, 
    procurement_items: List[Any] = None, 
    specifications: List[Any] = None,
    is_contractual: bool = False
) -> Dict[str, Any]:
    """
    Classifies a raw text candidate into the correct category, phase, and item association.
    """
    procurement_items = procurement_items or []
    specifications = specifications or []
    normalized = normalize_for_matching(candidate_text)

    # 1. Check for template instructions
    if is_template_instruction(normalized):
        return {"category": "TEMPLATE_INSTRUCTION", "status": "TEMPLATE_AUTO_DELETE"}

    # 2. Check Contractual
    if is_contractual:
        return {
            "category": RequirementCategory.CONTRACTUAL_TERM,
            "phase": RequirementPhase.CONTRACT_EXECUTION,
            "procurement_item_id": None,
            "flows_to_contract": True,
            "status": "PENDING_REVIEW"
        }

    # 3. Check CONTEXT
    if is_context(normalized, candidate_text):
        phase, flows = determine_phase_and_flow(RequirementCategory.CONTEXT, normalized)
        return {
            "category": RequirementCategory.CONTEXT,
            "phase": phase,
            "procurement_item_id": None,
            "flows_to_contract": flows,
            "status": "PENDING_REVIEW"
        }

    # 4. Check SELECTION_REQUIREMENT
    if is_selection_requirement(normalized):
        phase, flows = determine_phase_and_flow(RequirementCategory.SELECTION_REQUIREMENT, normalized)
        return {
            "category": RequirementCategory.SELECTION_REQUIREMENT,
            "phase": phase,
            "procurement_item_id": None,
            "flows_to_contract": flows,
            "status": "PENDING_REVIEW"
        }
        
    # 5. Explicit GENERAL_OBLIGATION
    if is_general_obligation(normalized):
        phase, flows = determine_phase_and_flow(RequirementCategory.GENERAL_OBLIGATION, normalized)
        return {
            "category": RequirementCategory.GENERAL_OBLIGATION,
            "phase": phase,
            "procurement_item_id": None,
            "flows_to_contract": flows,
            "status": "PENDING_REVIEW"
        }

    # 6. Check ITEM_SPECIFICATION vs GENERAL_OBLIGATION
    matched_item_id = match_procurement_item(normalized, procurement_items, specifications)
    
    if is_item_specification_keyword(normalized) or matched_item_id is not None:
        category = RequirementCategory.ITEM_SPECIFICATION
    else:
        category = RequirementCategory.GENERAL_OBLIGATION

    phase, flows = determine_phase_and_flow(category, normalized)
    
    status = "REVIEW_REQUIRED" if not matched_item_id and category == RequirementCategory.ITEM_SPECIFICATION else "PENDING_REVIEW"
    
    return {
        "category": category,
        "phase": phase,
        "procurement_item_id": matched_item_id,
        "flows_to_contract": flows,
        "status": status
    }
