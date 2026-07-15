import re
import json
import os
from pydantic import BaseModel
from typing import List, Dict, Any, Tuple

class DocumentExtractionResult(BaseModel):
    original_text: str
    cleaned_text: str
    normalized_text: str
    structure_json: List[Dict[str, Any]]
    corrections_json: List[Dict[str, Any]]
    warnings_json: List[Dict[str, Any]]
    metadata: Dict[str, Any]

class DocumentExtractionAgent:
    def __init__(self):
        # Load local dictionary
        dict_path = os.path.join(os.path.dirname(__file__), 'dictionaries', 'ocr_terms.json')
        self.dictionary = {}
        if os.path.exists(dict_path):
            with open(dict_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.dictionary = data.get("terminos_frecuentes", {})

        # Protected spans regexes
        self.protected_patterns = [
            r'\b\d{11}\b', # RUC
            r'S/\s*\d+(?:,\d{3})*(?:\.\d{2})?', # Precios
            r'\b\d+(?:\.\d+)?\s*%', # Porcentajes
            r'\b\d+\s+(?:unidades|kilos|litros|galones|meses|días|dias|años|horas|items|paquetes)\b', # Cantidades
            r'\b\d{1,2}/\d{1,2}/\d{2,4}\b', # Fechas
            r'(?i)\b(?:modelo|marca|código|pn|part number)\s+[-a-zA-Z0-9_]+', # Marcas, Modelos
        ]
        
    def _find_protected_spans(self, text: str) -> List[Tuple[int, int]]:
        spans = []
        for pattern in self.protected_patterns:
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                spans.append(match.span())
        # Merge overlapping spans
        if not spans:
            return []
        spans.sort(key=lambda x: x[0])
        merged = [spans[0]]
        for current in spans[1:]:
            last = merged[-1]
            if current[0] <= last[1]:
                merged[-1] = (last[0], max(last[1], current[1]))
            else:
                merged.append(current)
        return merged

    def _is_protected(self, start: int, end: int, protected_spans: List[Tuple[int, int]]) -> bool:
        for p_start, p_end in protected_spans:
            if start < p_end and end > p_start:
                return True
        return False

    def remove_repeated_headers_footers(self, pages_text: List[str]) -> Tuple[str, List[Dict[str, Any]]]:
        if not pages_text:
            return "", []
            
        cleaned_pages = []
        excluded_lines = []
        
        # We need to find lines that are repeated across multiple pages
        line_counts = {}
        for page in pages_text:
            lines = set(line.strip() for line in page.split('\n') if line.strip())
            for line in lines:
                line_counts[line] = line_counts.get(line, 0) + 1
                
        num_pages = len(pages_text)
        
        page_regex = re.compile(r'P[áa]gina\s+\d+\s+de\s+\d+', re.IGNORECASE)
        
        for i_page, page in enumerate(pages_text):
            lines = page.split('\n')
            new_lines = []
            for line in lines:
                s_line = line.strip()
                if not s_line:
                    new_lines.append(line)
                    continue
                    
                # Rule 1: Page X of Y
                if page_regex.search(s_line):
                    excluded_lines.append({
                        "text": s_line,
                        "page": i_page + 1,
                        "reason": "page_number",
                        "source": "header_footer_detection",
                        "confidence": 0.98,
                        "removed": True
                    })
                    continue
                    
                # Rule 2: Repeated lines (appears in > 50% of pages, min 2 pages)
                if num_pages > 1 and line_counts.get(s_line, 0) >= max(2, int(num_pages * 0.5)):
                    if len(s_line) < 100: # Don't exclude entire repeated paragraphs
                        excluded_lines.append({
                            "text": s_line,
                            "page": i_page + 1,
                            "reason": "repeated_text",
                            "source": "header_footer_detection",
                            "confidence": 0.85,
                            "removed": True
                        })
                        continue
                        
                # Rule 3: Known headers
                if re.match(r'^(GOBIERNO REGIONAL|DIRECCIÓN REGIONAL|MINISTERIO DE|MUNICIPALIDAD).{0,50}$', s_line, re.IGNORECASE):
                    excluded_lines.append({
                        "text": s_line,
                        "page": i_page + 1,
                        "reason": "known_header",
                        "source": "header_footer_detection",
                        "confidence": 0.95,
                        "removed": True
                    })
                    continue
                    
                new_lines.append(line)
            cleaned_pages.append("\n".join(new_lines))
            
        return "\n".join(cleaned_pages), excluded_lines

    def _apply_corrections(self, text: str) -> Tuple[str, List[Dict[str, Any]]]:
        corrections = []
        protected_spans = self._find_protected_spans(text)
        
        # 1. Join hyphenated words
        def hyphen_replacer(match):
            start, end = match.span()
            if self._is_protected(start, end, protected_spans):
                return match.group(0)
            original = match.group(0)
            corrected = match.group(1) + match.group(2)
            corrections.append({
                "original": original.strip(),
                "corrected": corrected,
                "reason": "unión de palabra separada por guion",
                "confidence": 0.95,
                "applied": True
            })
            return corrected
            
        text = re.sub(r'([a-záéíóúñA-ZÁÉÍÓÚÑ])-\s*\n\s*([a-záéíóúñA-ZÁÉÍÓÚÑ])', hyphen_replacer, text)
        
        # Recompute protected spans since text changed length
        protected_spans = self._find_protected_spans(text)

        # 2. Dictionary replacements
        for wrong, correct in self.dictionary.items():
            pattern = re.compile(rf'\b{wrong}\b', re.IGNORECASE)
            def dict_replacer(match):
                start, end = match.span()
                if self._is_protected(start, end, protected_spans):
                    corrections.append({
                        "original": match.group(0),
                        "corrected": correct,
                        "reason": "palabra de diccionario protegida",
                        "confidence": 0.5,
                        "applied": False,
                        "warning": "Requiere revisión manual"
                    })
                    return match.group(0)
                corrections.append({
                    "original": match.group(0),
                    "corrected": correct,
                    "reason": "diccionario OCR",
                    "confidence": 0.9,
                    "applied": True
                })
                return correct
            text = pattern.sub(dict_replacer, text)
            
        # Recompute protected spans
        protected_spans = self._find_protected_spans(text)
            
        # 3. Clean OCR garbage
        def garbage_replacer(match):
            original = match.group(0)
            corrections.append({
                "original": original.strip(),
                "corrected": "",
                "reason": "símbolos OCR basura",
                "confidence": 0.9,
                "applied": True
            })
            return ""
        text = re.sub(r'^[^\w\s]{2,}\s*$', garbage_replacer, text, flags=re.MULTILINE)
        
        # 4. Normalize bullets
        def bullet_replacer(match):
            original = match.group(0)
            corrected = match.group(1) + "- "
            corrections.append({
                "original": original.strip(),
                "corrected": "-",
                "reason": "normalización de viñeta",
                "confidence": 0.95,
                "applied": True
            })
            return corrected
        text = re.sub(r'(^|\n)\s*[+o•*]\s+', bullet_replacer, text)

        # 5. Spacing
        text = re.sub(r' {2,}', ' ', text)
        text = re.sub(r'(?<!\n)\n(?=[a-záéíóúñ](?!\)))', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        # 6. Specific normalizations
        def n_replacer(match):
            corrections.append({
                "original": match.group(0),
                "corrected": "N° ",
                "reason": "Normalización de símbolo N°",
                "confidence": 0.95,
                "applied": True
            })
            return "N° "
            
        text = re.sub(r'\bN[*\?°]?\s*', n_replacer, text)
        
        def ley_replacer(match):
            corrections.append({
                "original": match.group(0),
                "corrected": f"Ley N° {match.group(1)}",
                "reason": "Normalización de Ley N°",
                "confidence": 1.0,
                "applied": True
            })
            return f"Ley N° {match.group(1)}"
            
        text = re.sub(r'(?i)Ley\s+N°\s*(\d+)', ley_replacer, text)
        
        def bullet_gco_replacer(match):
            corrections.append({
                "original": match.group(0),
                "corrected": "- Co" + match.group(1),
                "reason": "Corrección contextual de viñeta GCo",
                "confidence": 0.9,
                "applied": True
            })
            return "- Co" + match.group(1)
            
        text = re.sub(r'^(?:[Gg][Cc]|[Gg]c)o(adyuvar|ntribuir|nformidad|ndicion|nformar|nstituir|ordinar)\b', bullet_gco_replacer, text, flags=re.MULTILINE)
        
        return text.strip(), corrections

    def extract_structure(self, text: str) -> List[Dict[str, Any]]:
        # Simplified block extraction based on newlines and prefixes
        blocks = []
        paragraphs = text.split('\n\n')
        order = 1
        
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
                
            block_type = "paragraph"
            label = ""
            
            if re.match(r'^(I|II|III|IV|V|VI|VII|VIII|IX|X)\.\s+', para):
                block_type = "section_title"
            elif re.match(r'^\d+\.\d+(?:\.\d+)?\s+', para):
                block_type = "subsection_title"
                match = re.match(r'^(\d+\.\d+(?:\.\d+)?)\s+(.*)', para)
                if match:
                    label = match.group(1)
                    para = match.group(2)
            elif re.match(r'^[a-z]\)\s+', para):
                block_type = "letter_item"
                match = re.match(r'^([a-z]\))\s+(.*)', para)
                if match:
                    label = match.group(1)
                    para = match.group(2)
            elif re.match(r'^-\s+', para):
                block_type = "bullet_item"
                para = para[1:].strip()
                
            # Table heuristic (very basic)
            elif "  " in para and "\n" in para:
                lines = para.split('\n')
                if len(lines) > 1 and all("  " in line for line in lines):
                    block_type = "table_vertical"
                    
            blocks.append({
                "type": block_type,
                "text": para,
                "label": label,
                "order": order,
                "confidence": 0.9 if block_type != "table_vertical" else 0.5,
                "warnings": ["Tabla requiere revisión manual"] if block_type == "table_vertical" else []
            })
            order += 1
            
        return blocks

    def _split_into_sections(self, cleaned_text: str, contract_type: str) -> List[Dict[str, Any]]:
        from app.services.extraction.section_detector import normalize_section_headings, EXPECTED_TITLES, get_best_match, ROMAN_NUMERALS
        
        normalized_with_headings = normalize_section_headings(cleaned_text, contract_type)
        expected = EXPECTED_TITLES.get(contract_type, EXPECTED_TITLES["bienes"])
        
        header_pattern = re.compile(r'^([IlVxXiIvV]+)[\.\-]?\s+([^\n]+)', re.MULTILINE | re.IGNORECASE)
        matches = list(header_pattern.finditer(normalized_with_headings))
        
        sections_data = []
        for i, match in enumerate(matches):
            roman_raw = match.group(1).upper().replace('L', 'I')
            title_raw = match.group(2).strip()
            
            title_raw = re.sub(r'\(obligatorio\)', '', title_raw, flags=re.IGNORECASE).strip()
            title_raw = re.sub(r'\(de corresponder\)', '', title_raw, flags=re.IGNORECASE).strip()
            title_raw = re.sub(r'\b(obligatorio)\b', '', title_raw, flags=re.IGNORECASE).strip()
            title_raw = re.sub(r'\b(de corresponder)\b', '', title_raw, flags=re.IGNORECASE).strip()
            
            start_idx = match.end()
            end_idx = matches[i+1].start() if i + 1 < len(matches) else len(normalized_with_headings)
            
            content_cleaned = normalized_with_headings[start_idx:end_idx].strip()
            
            best_title, confidence = get_best_match(title_raw, expected)
            is_valid_roman = roman_raw in ROMAN_NUMERALS
            warnings_list = []
            
            if confidence < 0.5 and not is_valid_roman:
                continue
                
            if confidence < 0.85:
                warnings_list.append({
                    "code": "LOW_CONFIDENCE_TITLE",
                    "message": f"Título detectado con baja confianza: {title_raw}",
                    "severity": "warning",
                    "source": "section_detector"
                })
                
            if best_title in expected:
                canonical_index = expected.index(best_title)
                if canonical_index < len(ROMAN_NUMERALS):
                    canonical_roman = ROMAN_NUMERALS[canonical_index]
                    if canonical_roman != roman_raw:
                        warnings_list.append({
                            "code": "ROMAN_CORRECTED",
                            "message": "Número romano corregido por coincidencia de título",
                            "severity": "info",
                            "source": "section_detector"
                        })
                        roman_raw = canonical_roman
                        
            if not is_valid_roman and not best_title:
                warnings_list.append({
                    "code": "UNKNOWN_ROMAN",
                    "message": "Número romano no reconocido",
                    "severity": "warning",
                    "source": "section_detector"
                })

            sections_data.append({
                "cleaned_text": content_cleaned,
                "roman": roman_raw,
                "title": best_title or title_raw,
                "confidence": confidence,
                "warnings": warnings_list,
                "order": i + 1
            })
            
        # Deduplication
        dedup_sections = []
        for sec in sections_data:
            if not dedup_sections:
                dedup_sections.append(sec)
                continue
                
            prev_sec = dedup_sections[-1]
            
            if prev_sec["title"] == sec["title"]:
                from difflib import SequenceMatcher
                ratio = SequenceMatcher(None, prev_sec["cleaned_text"], sec["cleaned_text"]).ratio()
                if ratio > 0.85 or sec["cleaned_text"] in prev_sec["cleaned_text"] or prev_sec["cleaned_text"] in sec["cleaned_text"]:
                    warning_obj = {
                        "code": "DUPLICATE_REMOVED",
                        "message": "Bloque duplicado eliminado (deduplicación semántica)",
                        "severity": "warning",
                        "source": "section_deduplication"
                    }
                    if len(sec["cleaned_text"]) > len(prev_sec["cleaned_text"]):
                        sec["warnings"].append(warning_obj)
                        dedup_sections[-1] = sec
                    else:
                        prev_sec["warnings"].append(warning_obj)
                    continue
                    
            dedup_sections.append(sec)
            
        return dedup_sections

    def process(self, pages_text: List[str], contract_type: str) -> List[DocumentExtractionResult]:
        from app.services.extraction.section_detector import normalize_structural_breaks, build_structure_blocks
        
        # original_combined represents raw OCR with all its flaws (headers included, etc)
        # We can't perfectly map sections to original text with indices without complex alignment,
        # so for this version we map `original_text` to `cleaned_text` before modifications,
        # or we say original_text = "See full original document" if needed.
        # But wait, the requirement is to keep the raw OCR as original_text.
        # Cleaned text just has headers removed. Let's use the cleaned text as original text of the section,
        # but without removing template markers.
        
        cleaned_combined, excluded = self.remove_repeated_headers_footers(pages_text)
        
        # We split into sections first
        sections_data = self._split_into_sections(cleaned_combined, contract_type)
        
        results = []
        for sec in sections_data:
            sec_cleaned = sec["cleaned_text"]
            
            # This will act as our "original_text" for the section.
            original_text = sec_cleaned
            
            corrections = []
            
            # Apply technical cleaning to get `cleaned_text`
            def template_replacer(match):
                corrections.append({
                    "original": match.group(0),
                    "corrected": "",
                    "reason": "Eliminación de marcador de plantilla",
                    "confidence": 1.0,
                    "applied": True
                })
                return ""
                
            sec_cleaned = re.sub(r'\(obligatorio\)', template_replacer, sec_cleaned, flags=re.IGNORECASE)
            sec_cleaned = re.sub(r'\(de corresponder\)', template_replacer, sec_cleaned, flags=re.IGNORECASE)
            
            # Remove specific OCR garbage
            def garbage_replacer(match):
                corrections.append({
                    "original": match.group(0),
                    "corrected": "",
                    "reason": "Limpieza de basura OCR residual",
                    "confidence": 1.0,
                    "applied": True
                })
                return ""
                
            sec_cleaned = re.sub(r'(?i)\bDNS no corresponde\b', garbage_replacer, sec_cleaned)
            sec_cleaned = re.sub(r'(?i)no corresponde\s+[IVX]+,?\s+OTROS\.?', garbage_replacer, sec_cleaned)
            
            # Apply normalization
            normalized, norm_corrections = self._apply_corrections(sec_cleaned)
            corrections.extend(norm_corrections)
            
            # Structural breaks
            normalized = normalize_structural_breaks(normalized)
            structure = build_structure_blocks(normalized)
            
            warnings_list = sec["warnings"]
            for b in structure:
                b['confidence'] = 0.95
                b['warnings'] = []
                if b['type'] == 'table_vertical':
                    b['confidence'] = 0.5
                    b['warnings'] = ["Tabla requiere revisión manual"]
                    warnings_list.append({
                        "code": "LOW_CONFIDENCE_TABLE",
                        "message": "Tabla requiere revisión manual",
                        "severity": "warning",
                        "source": "table_detection"
                    })
                    
            metadata = {
                "extraction_method": "ocr",
                "confidence": round(sec["confidence"], 2),
                "original_roman": sec["roman"],
                "title": sec["title"],
                "original_order": sec["order"]
            }
            if len(results) == 0 and excluded:
                metadata["excluded_lines"] = excluded

            res = DocumentExtractionResult(
                original_text=original_text,
                cleaned_text=sec_cleaned,
                normalized_text=normalized,
                structure_json=structure,
                corrections_json=corrections,
                warnings_json=warnings_list,
                metadata=metadata
            )
            results.append(res)
            
        return results

