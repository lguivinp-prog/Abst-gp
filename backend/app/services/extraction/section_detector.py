import re
import difflib
from typing import List, Dict, Any
from pydantic import BaseModel
from app.services.ocr.cleaner import normalize_structural_breaks

_NARRATIVE_INTRO_ENDINGS = (
    "los siguientes",
    "las siguientes",
    "lo siguiente",
    "a continuación",
)

def _is_narrative_intro(key: str) -> bool:
    normalized = " ".join(key.casefold().split())
    return normalized.endswith(_NARRATIVE_INTRO_ENDINGS)

class DetectedSection(BaseModel):
    original_roman: str
    original_order: int
    title: str
    original_text: str
    structure_json: List[Dict[str, Any]] = []
    confidence_score: float
    warnings: str
    review_status: str

# Diccionarios de títulos esperados por tipo
EXPECTED_TITLES = {
    "bienes": [
        "FINALIDAD PÚBLICA", "ANTECEDENTES", "OBJETIVO DE LA CONTRATACIÓN",
        "JUSTIFICACIÓN DE LOS BIENES A CONTRATAR", "CARACTERÍSTICAS Y CONDICIONES DE LA CONTRATACIÓN",
        "CRONOGRAMA DE ENTREGA", "REQUISITOS Y RECURSOS DEL PROVEEDOR", "LUGAR Y PLAZO DE LA PRESTACIÓN",
        "CONFORMIDAD DEL BIEN", "FORMA DE PAGO", "CONSIDERACIONES PARA LA EJECUCIÓN CONTRACTUAL",
        "PENALIDADES", "OTRAS CARACTERÍSTICAS QUE SEAN RELEVANTES PARA LA CONTRATACIÓN"
    ],
    "servicios": [
        "FINALIDAD PÚBLICA", "ANTECEDENTES", "OBJETIVO DE LA CONTRATACIÓN",
        "JUSTIFICACIÓN DE LA NECESIDAD DE LA CONTRATACIÓN", "CARACTERÍSTICAS Y CONDICIONES DE LA CONTRATACIÓN",
        "PRODUCTOS O ENTREGABLES", "REQUISITOS Y RECURSOS DEL PROVEEDOR", "RESULTADOS ESPERADOS",
        "LUGAR Y PLAZO DE LA PRESTACIÓN", "CONFORMIDAD DE LA PRESTACIÓN", "FORMA DE PAGO",
        "PENALIDADES", "OTRAS CONSIDERACIONES PARA LA EJECUCIÓN DE LA PRESTACIÓN",
        "OTRAS CARACTERÍSTICAS QUE SEAN RELEVANTES PARA LA CONTRATACIÓN"
    ]
}

# Expandir aliases y variaciones permitidas para mejor fuzzy matching
ROMAN_NUMERALS = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII", "XIV"]

def get_best_match(target: str, choices: List[str]) -> tuple[str, float]:
    """Devuelve la mejor coincidencia y su ratio usando difflib"""
    best_match = None
    highest_ratio = 0.0
    for choice in choices:
        ratio = difflib.SequenceMatcher(None, target.upper(), choice.upper()).ratio()
        if ratio > highest_ratio:
            highest_ratio = ratio
            best_match = choice
    return best_match, highest_ratio

def build_structure_blocks(text: str) -> List[Dict[str, Any]]:
    """Convierte el texto en bloques estructurados."""
    blocks = []
    lines = text.split('\n')
    current_paragraph = []
    order = 1
    
    in_table = False
    current_table_rows = []

    def flush_table():
        nonlocal in_table, current_table_rows, order
        if in_table and current_table_rows:
            blocks.append({
                "type": "table_vertical",
                "rows": current_table_rows,
                "order": order
            })
            order += 1
            in_table = False
            current_table_rows = []

    def flush_paragraph():
        nonlocal order
        flush_table()
        if current_paragraph:
            blocks.append({
                "type": "paragraph",
                "text": " ".join(current_paragraph).strip(),
                "order": order
            })
            order += 1
            current_paragraph.clear()

    # Regexes para detectar inicios de ítem
    num_item_re = re.compile(r'^((?:[IVX]+\.)?\d+(?:\.\d+)*[\.\)]?)\s+(.*)', re.IGNORECASE)
    letter_item_re = re.compile(r'^([a-z]\))\s+(.*)')
    bullet_item_re = re.compile(r'^([\-\•\*\>\+o])\s*(.*)')

    # Títulos generales sin numeral
    general_titles_re = re.compile(r'^(Objetivo General|Objetivos Específicos|Productos o entregables|Resultados esperados|Lugar y plazo|Forma de pago|Penalidades|Garantía comercial|Garantía|Descripción|Alcance|Condiciones|Requisitos|Lugar de entrega|Plazo):?\s*$', re.IGNORECASE)

    def parse_table_row(row_str):
        m = re.match(r'^(\d+)\s+(.*?)\s+(Unidad|Caja|Paquete|Gal[óo]n|Litro|Servicio|Kit|Envase|Bolsa|Frasco|Kilo|Gramo|Cilindro)\s+(\d+)\s+(.*)$', row_str, re.IGNORECASE)
        if m:
            chars_raw = m.group(5).strip()
            # Parse commas to lists for features if it looks like a list
            chars = [c.strip().capitalize() for c in re.split(r'[,;]', chars_raw) if c.strip()]
            return {
                "Item": m.group(1),
                "Bien": m.group(2).strip(),
                "Unidad de medida": m.group(3).capitalize(),
                "Cantidad": m.group(4),
                "Características técnicas": chars if len(chars) > 1 else [chars_raw]
            }
        return None

    pending_key = None

    for line in lines:
        line_s = line.strip()
        if not line_s:
            flush_paragraph()
            pending_key = None
            continue
            
        # Limpieza de (obligatorio) suelto en la línea, que a veces queda
        line_s = re.sub(r'\(obligatorio\)', '', line_s, flags=re.IGNORECASE).strip()
        line_s = re.sub(r'\(de corresponder\)', '', line_s, flags=re.IGNORECASE).strip()
        
        if not line_s:
            continue

        if in_table and not pending_key:
            parsed = parse_table_row(line_s)
            if parsed:
                current_table_rows.append(parsed)
                continue
            else:
                flush_table()
                # Line might be something else, continue parsing it below
        
        # Horizontal table detection
        table_header_match = re.search(r'Item\s+Bien\s+Unidad\s+de\s+medida\s+Cantidad\s+Características\s+técnicas(.*)', line_s, re.IGNORECASE)
        if table_header_match:
            flush_paragraph()
            rest_of_line = table_header_match.group(1).strip()
            
            if rest_of_line:
                parsed = parse_table_row(rest_of_line)
                if parsed:
                    in_table = True
                    current_table_rows.append(parsed)
                    continue
                else:
                    blocks.append({
                        "type": "warning",
                        "text": "Tabla detectada, requiere revisión manual",
                        "order": order
                    })
                    order += 1
                    current_paragraph.append("Item Bien Unidad de medida Cantidad Características técnicas " + rest_of_line)
            else:
                in_table = True
            continue

        # Key-Value table heuristic
        kv_match = re.match(r'^([A-Z][a-záéíóúñA-ZÁÉÍÓÚÑ\s/]+):\s*(.*)$', line_s)
        if kv_match:
            key, val = kv_match.group(1).strip(), kv_match.group(2).strip()
            if _is_narrative_intro(key):
                current_paragraph.append(line_s)
                continue

            if not in_table or (in_table and current_table_rows and "Item" in current_table_rows[-1]):
                flush_paragraph() # flush anything else
                in_table = True
            
            if val:
                current_table_rows.append({key: val})
                pending_key = None
            else:
                pending_key = key
            continue
            
        if pending_key:
            current_table_rows.append({pending_key: line_s})
            pending_key = None
            continue

        gen_title_match = general_titles_re.match(line_s)
        if gen_title_match:
            flush_paragraph()
            blocks.append({
                "type": "subsection_title",
                "label": "",
                "text": gen_title_match.group(1).strip(),
                "order": order,
                "level": 1
            })
            order += 1
            continue

        num_match = num_item_re.match(line_s)
        if num_match:
            flush_paragraph()
            label = num_match.group(1)
            text_content = num_match.group(2).strip()
            
            # If text_content is very short or looks like a title without period at the end
            block_type = "subsection_title" if not text_content.endswith('.') and len(text_content.split()) < 15 else "numbered_item"
            
            # Additional constraint: if the user passes e.g. "13.1 Penalidad", we should split it if next line is a paragraph? 
            # Actually, the requirement says "El sistema debe separar: 13.1 Penalidad de su párrafo siguiente."
            # Our code already treats it as a single block (subsection_title) if it's short, and the next line becomes a paragraph.
            # So this is naturally handled because next line won't match num_match.
            
            blocks.append({
                "type": block_type,
                "label": label,
                "text": text_content,
                "order": order,
                "level": len(label.split('.'))
            })
            order += 1
            continue
            
        letter_match = letter_item_re.match(line_s)
        if letter_match:
            flush_paragraph()
            blocks.append({
                "type": "letter_item",
                "label": letter_match.group(1),
                "text": letter_match.group(2).strip(),
                "order": order,
                "level": 1
            })
            order += 1
            continue
            
        bullet_match = bullet_item_re.match(line_s)
        if bullet_match:
            flush_paragraph()
            blocks.append({
                "type": "bullet_item",
                "label": "-",
                "text": bullet_match.group(2).strip(),
                "order": order,
                "level": 1
            })
            order += 1
            continue

        current_paragraph.append(line_s)

    flush_paragraph()
    return blocks

def normalize_section_headings(text: str, contract_type: str = "bienes") -> str:
    """Inserta saltos de línea antes y después de los títulos romanos si están inline."""
    expected = EXPECTED_TITLES.get(contract_type, EXPECTED_TITLES["bienes"])
    sorted_titles = sorted(expected, key=len, reverse=True)
    
    for title in sorted_titles:
        roman_pattern = r'[IlVxXiIvV]+[\.\-]?'
        escaped_title = re.escape(title)
        
        # Inline before title
        p1 = re.compile(r'([^\n])\s*(' + roman_pattern + r'\s+' + escaped_title + r')\s+([^\n])', re.IGNORECASE)
        text = p1.sub(r'\1\n\2\n\3', text)
        
        # At start of line but with trailing text
        p2 = re.compile(r'^(' + roman_pattern + r'\s+' + escaped_title + r')\s+([^\n])', re.IGNORECASE | re.MULTILINE)
        text = p2.sub(r'\1\n\2', text)
        
    return text

def extract_sections(text: str, contract_type: str = "bienes") -> List[DetectedSection]:
    """
    Detecta secciones con números romanos en el texto.
    """
    text = normalize_section_headings(text, contract_type)
    expected = EXPECTED_TITLES.get(contract_type, EXPECTED_TITLES["bienes"])
    
    header_pattern = re.compile(r'^([IlVxXiIvV]+)[\.\-]?\s+([^\n]+)', re.MULTILINE | re.IGNORECASE)
    
    matches = list(header_pattern.finditer(text))
    sections = []
    
    for i, match in enumerate(matches):
        roman_raw = match.group(1).upper().replace('L', 'I')
        title_raw = match.group(2).strip()
        
        # Eliminar marcadores de plantilla en el título
        title_raw = re.sub(r'\(obligatorio\)', '', title_raw, flags=re.IGNORECASE).strip()
        title_raw = re.sub(r'\(de corresponder\)', '', title_raw, flags=re.IGNORECASE).strip()
        title_raw = re.sub(r'\b(obligatorio)\b', '', title_raw, flags=re.IGNORECASE).strip()
        title_raw = re.sub(r'\b(de corresponder)\b', '', title_raw, flags=re.IGNORECASE).strip()
        
        start_idx = match.end()
        end_idx = matches[i+1].start() if i + 1 < len(matches) else len(text)
        
        content = text[start_idx:end_idx].strip()
        
        best_title, confidence = get_best_match(title_raw, expected)
        
        is_valid_roman = roman_raw in ROMAN_NUMERALS
        warnings_list = []
        review_status = "validated"
        
        if confidence < 0.5 and not is_valid_roman:
            continue
            
        if confidence < 0.85:
            warnings_list.append(f"Título detectado con baja confianza: {title_raw}")
            review_status = "pending_review"
            
        # Mapeo Canónico Romano
        if best_title in expected:
            canonical_index = expected.index(best_title)
            if canonical_index < len(ROMAN_NUMERALS):
                canonical_roman = ROMAN_NUMERALS[canonical_index]
                if canonical_roman != roman_raw:
                    warnings_list.append("Número romano corregido por coincidencia de título")
                    roman_raw = canonical_roman
            
        order = i + 1
        if not is_valid_roman and not best_title:
            warnings_list.append("Número romano no reconocido")
            review_status = "pending_review"

        cleaned_content = normalize_structural_breaks(content)

        sections.append(DetectedSection(
            original_roman=roman_raw,
            original_order=order,
            title=best_title or title_raw,
            original_text=content,
            structure_json=build_structure_blocks(cleaned_content),
            confidence_score=round(confidence, 2),
            warnings=" | ".join(warnings_list),
            review_status=review_status
        ))
        
    # Deduplication
    dedup_sections = []
    for sec in sections:
        if not dedup_sections:
            dedup_sections.append(sec)
            continue
            
        prev_sec = dedup_sections[-1]
        
        if prev_sec.title == sec.title:
            ratio = difflib.SequenceMatcher(None, prev_sec.original_text, sec.original_text).ratio()
            # If they are very similar or one is contained in the other
            if ratio > 0.85 or sec.original_text in prev_sec.original_text or prev_sec.original_text in sec.original_text:
                # Keep the longest one
                if len(sec.original_text) > len(prev_sec.original_text):
                    # Copy warnings from prev_sec to sec
                    warn_str = sec.warnings + " | " if sec.warnings else ""
                    sec.warnings = warn_str + "Bloque duplicado eliminado (deduplicación)"
                    dedup_sections[-1] = sec
                else:
                    warn_str = prev_sec.warnings + " | " if prev_sec.warnings else ""
                    prev_sec.warnings = warn_str + "Bloque duplicado eliminado (deduplicación)"
                continue
                
        dedup_sections.append(sec)
        
    return dedup_sections
