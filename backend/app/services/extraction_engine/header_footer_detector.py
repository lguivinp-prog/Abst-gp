import difflib
import re
from collections import defaultdict
from app.services.extraction_engine.models.document import StructuredDocument, DocumentBlock

class HeaderFooterDetector:
    def __init__(self, repetition_threshold: float = 0.4, similarity_threshold: float = 0.85):
        self.repetition_threshold = repetition_threshold
        self.similarity_threshold = similarity_threshold
        self.page_num_pattern = re.compile(r'^(p[aá]gina\s*)?\d+(\s*(de|/|-)\s*\d+)?$', re.IGNORECASE)

    def process(self, document: StructuredDocument) -> StructuredDocument:
        if not document.pages:
            return document
            
        total_pages = len(document.pages)
        if total_pages < 2:
            return document

        page_texts = defaultdict(list)
        for block in document.blocks:
            if isinstance(block.content, str):
                page_texts[block.page].append((block, block.content.strip()))
                
        blocks_to_remove = set()
        
        for p1, blocks1 in page_texts.items():
            for b1, text1 in blocks1:
                if len(text1) < 4: 
                    continue
                    
                if id(b1) in blocks_to_remove:
                    continue
                    
                pages_with_match = {p1}
                matching_blocks = [b1]
                
                for p2, blocks2 in page_texts.items():
                    if p1 == p2:
                        continue
                    for b2, text2 in blocks2:
                        if id(b2) in blocks_to_remove:
                            continue
                        
                        seq = difflib.SequenceMatcher(None, text1, text2)
                        if seq.ratio() >= self.similarity_threshold:
                            pages_with_match.add(p2)
                            matching_blocks.append(b2)
                            break 
                            
                # If it appears in >= threshold% of pages (e.g. 40%), or at least 3 pages
                required_pages = max(2, int(total_pages * self.repetition_threshold))
                if len(pages_with_match) >= required_pages:
                    for mb in matching_blocks:
                        blocks_to_remove.add(id(mb))
                        mb.style["remove_from_content"] = True
                        y = mb.bounding_box.get("y", 500)
                        if y < 300: 
                            mb.type = "header"
                        else:
                            mb.type = "footer"
                            
        # Detect page numbers (isolated numbers or "Page X of Y")
        for block in document.blocks:
            if isinstance(block.content, str) and id(block) not in blocks_to_remove:
                text = block.content.strip()
                if self.page_num_pattern.match(text):
                    block.style["remove_from_content"] = True
                    y = block.bounding_box.get("y", 500)
                    if y < 300:
                        block.type = "header"
                    else:
                        block.type = "footer"
        
        return document
