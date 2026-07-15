import re
import difflib
from app.services.extraction_engine.models.document import StructuredDocument, DocumentBlock
from app.services.extraction_engine.config import contract_config

class SemanticSectionParser:
    def __init__(self):
        self.roman_pattern = re.compile(r'^\s*[\-\•\*]?\s*(I{1,3}|IV|V|VI{1,3}|IX|X|XI{1,3})[\.\-\:]?\s+(.*)$', re.IGNORECASE)
        self.decimal_pattern = re.compile(r'^(\d+\.\d+(?:\.\d+)?)\s+(.*)$')
        self.known_sections = contract_config.EXPECTED_SECTIONS_BIENES + contract_config.EXPECTED_SUBSECTIONS
        
        self.known_subsections = [
            "Descripción y cantidad",
            "Características técnicas",
            "Condiciones de entrega",
            "Condiciones de pago",
            "Embalaje y rotulado",
            "Transporte"
        ]
        
    def process(self, document: StructuredDocument) -> StructuredDocument:
        for block in document.blocks:
            if block.style.get("remove_from_content"):
                continue
                
            if isinstance(block.content, str):
                text = block.content.strip()
                block.original_text = text
                
                roman_match = self.roman_pattern.match(text)
                if roman_match:
                    numeral = roman_match.group(1)
                    section_name = roman_match.group(2)
                    block.type = "section"
                    block.normalized_text = f"{numeral.upper()}. {self._normalize_title(section_name, is_major=True)}"
                    continue
                    
                matches = difflib.get_close_matches(text.upper(), self.known_sections, n=1, cutoff=contract_config.SECTION_FUZZY_THRESHOLD)
                if matches:
                    block.type = "section"
                    block.normalized_text = matches[0]
                    continue
                    
                # Substring matching fallback
                text_clean = re.sub(r'[^\w\s]', ' ', text.upper())
                text_clean = re.sub(r'\s+', ' ', text_clean).strip()
                
                found_match = False
                for known in self.known_sections:
                    k_clean = re.sub(r'[^\w\s]', ' ', known.upper())
                    k_clean = re.sub(r'\s+', ' ', k_clean).strip()
                    if k_clean in text_clean and len(text) < len(known) + 50:
                        block.type = "section"
                        block.normalized_text = known
                        found_match = True
                        break
                if found_match:
                    continue
                    
                decimal_match = self.decimal_pattern.match(text)
                if decimal_match:
                    numeral = decimal_match.group(1)
                    section_name = decimal_match.group(2)
                    block.type = "subsection"
                    block.normalized_text = f"{numeral} {self._normalize_title(section_name, is_major=False)}"
                    continue
                    
                block.normalized_text = text.replace("  ", " ").strip()
                
        return document
        
    def _normalize_title(self, title: str, is_major: bool) -> str:
        choices = self.known_sections if is_major else self.known_subsections
        target = title.upper() if is_major else title
        matches = difflib.get_close_matches(target, choices, n=1, cutoff=0.7)
        if matches:
            return matches[0]
            
        # Substring fallback
        target_clean = re.sub(r'[^\w\s]', ' ', target)
        target_clean = re.sub(r'\s+', ' ', target_clean).strip().upper()
        
        for known in choices:
            k_clean = re.sub(r'[^\w\s]', ' ', known)
            k_clean = re.sub(r'\s+', ' ', k_clean).strip().upper()
            if k_clean in target_clean:
                return known
                
        return title.strip()
