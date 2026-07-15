from typing import List, Dict, Any
import re
from app.services.extraction_engine.models.document import OcrElement

class LayoutAnalyzer:
    def __init__(self):
        # List markers: bullet points, letters, numbers, roman numerals
        self.list_pattern = re.compile(r'^(\-|\•|\d+\.|\d+\.\d+(\.\d+)*|[a-z]\)|[IVX]+\.)\s+')
        
        # Roman numerals I, II, ..., XIV
        self.roman_pattern = re.compile(r'^\s*[\-\•\*]?\s*(I{1,3}|IV|V|VI{1,3}|IX|X|XI{1,3}|XIV)[\.\-\:]?\s+', re.IGNORECASE)
        # Decimal numerals 5.1, 8.2.1
        self.decimal_pattern = re.compile(r'^(\d+\.\d+(?:\.\d+)?)\s+')

    def analyze(self, elements: List[OcrElement]) -> Dict[str, Any]:
        if not elements:
            return {"blocks": []}
            
        # 1. Sort elements roughly top-to-bottom, left-to-right
        elements = sorted(elements, key=lambda e: (round(e.y / 10) * 10, e.x))
        
        # 2. Group into lines
        lines = []
        current_line = []
        current_y = None
        
        for el in elements:
            if current_y is None:
                current_line.append(el)
                current_y = el.y
            else:
                if abs(el.y - current_y) < (el.height * 0.5):
                    current_line.append(el)
                else:
                    lines.append(current_line)
                    current_line = [el]
                    current_y = el.y
                    
        if current_line:
            lines.append(current_line)
            
        # Convert lines to text strings and bounding boxes
        merged_lines = []
        for line in lines:
            line = sorted(line, key=lambda e: e.x)
            text = " ".join([e.text for e in line])
            
            x = min(e.x for e in line)
            y = min(e.y for e in line)
            w = max(e.x + e.width for e in line) - x
            h = max(e.y + e.height for e in line) - y
            
            merged_lines.append({
                "text": text,
                "x": x,
                "y": y,
                "width": w,
                "height": h,
                "elements": line
            })
            
        blocks = []
        current_block_type = None
        current_block_text = []
        current_block_lines = []
        
        avg_height = sum([l["height"] for l in merged_lines]) / len(merged_lines) if merged_lines else 10
        
        def flush_block():
            if current_block_text:
                min_x = min(l["x"] for l in current_block_lines)
                min_y = min(l["y"] for l in current_block_lines)
                max_w = max(l["x"] + l["width"] for l in current_block_lines)
                max_h = max(l["y"] + l["height"] for l in current_block_lines)
                
                block_elements = []
                total_conf = 0.0
                count = 0
                for l in current_block_lines:
                    for el in l["elements"]:
                        block_elements.append(el)
                        total_conf += el.confidence
                        count += 1
                        
                blocks.append({
                    "type": current_block_type,
                    "text": " ".join(current_block_text) if current_block_type != "list" else "\n".join(current_block_text),
                    "bounding_box": {"x": min_x, "y": min_y, "w": max_w - min_x, "h": max_h - min_y},
                    "source_elements": block_elements,
                    "confidence": total_conf / count if count > 0 else 0.0,
                    "transformations": ["semantic_layout_grouping"]
                })
        
        for idx, line in enumerate(merged_lines):
            text = line["text"].strip()
            if not text:
                continue
                
            # SEMANTIC SPLIT RULES (Highest priority)
            is_roman = bool(self.roman_pattern.match(text))
            is_decimal = bool(self.decimal_pattern.match(text))
            
            # Remove height requirement, just look for short ALL CAPS lines
            is_all_caps = text.isupper() and 4 < len(text) < 100
            
            # Check if it starts with a known section (fallback for bad roman numerals)
            from app.services.extraction_engine.config.contract_config import EXPECTED_SECTIONS_BIENES, EXPECTED_SECTIONS_SERVICIOS
            known_all = EXPECTED_SECTIONS_BIENES + EXPECTED_SECTIONS_SERVICIOS
            
            text_clean = re.sub(r'[^\w\s]', ' ', text.upper())
            text_clean = re.sub(r'\s+', ' ', text_clean).strip()
            
            is_known_section = False
            for k in known_all:
                k_clean = re.sub(r'[^\w\s]', ' ', k.upper())
                k_clean = re.sub(r'\s+', ' ', k_clean).strip()
                if k_clean in text_clean and len(text) < 200:
                    is_known_section = True
                    break
            
            large_vertical_gap = False
            alignment_change = False
            
            if current_block_lines:
                last_line = current_block_lines[-1]
                if line["y"] - (last_line["y"] + last_line["height"]) > (avg_height * 1.2):
                    large_vertical_gap = True
                if abs(line["x"] - last_line["x"]) > 20:
                    alignment_change = True
                    
            force_split = is_roman or is_decimal or is_all_caps or is_known_section or large_vertical_gap or alignment_change
            
            if force_split and current_block_text:
                flush_block()
                current_block_text = []
                current_block_lines = []
                current_block_type = None
                
            if is_roman or is_decimal or is_all_caps:
                current_block_type = "heading"
                current_block_text = [text]
                current_block_lines = [line]
                flush_block()
                current_block_text = []
                current_block_lines = []
                current_block_type = None
                continue
                
            # List heuristics
            is_list = bool(self.list_pattern.match(text))
            
            if is_list:
                if current_block_text and current_block_type != "list":
                    flush_block()
                    current_block_text = []
                    current_block_lines = []
                    
                current_block_type = "list"
                current_block_text.append(text)
                current_block_lines.append(line)
                
            else:
                if current_block_type == "paragraph":
                    current_block_text.append(text)
                    current_block_lines.append(line)
                else:
                    if current_block_text:
                        flush_block()
                    current_block_type = "paragraph"
                    current_block_text = [text]
                    current_block_lines = [line]
                    
        flush_block()
            
        return {"blocks": blocks}
