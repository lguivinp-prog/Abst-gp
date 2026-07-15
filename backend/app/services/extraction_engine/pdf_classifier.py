import fitz  # PyMuPDF
from typing import Dict, Any
from app.services.extraction_engine.models.document import PdfClassificationResult

class PdfClassifier:
    def __init__(self, text_length_threshold: int = 150):
        # A scanned page might have some garbage OCR layer if not properly cleaned,
        # but usually it's near zero or very few characters.
        self.text_length_threshold = text_length_threshold

    def classify(self, pdf_path: str) -> PdfClassificationResult:
        doc = fitz.open(pdf_path)
        pages_count = len(doc)
        text_pages = 0
        image_pages = 0
        
        for i in range(pages_count):
            page = doc[i]
            text = page.get_text("text").strip()
            
            # Also check images to be more robust
            images = page.get_images(full=True)
            
            if len(text) > self.text_length_threshold:
                text_pages += 1
            else:
                image_pages += 1
                
        doc.close()

        if pages_count == 0:
            doc_type = "unknown"
            confidence = 0.0
        elif text_pages == pages_count:
            doc_type = "digital"
            confidence = 0.98
        elif image_pages == pages_count:
            doc_type = "scanned"
            confidence = 0.95
        else:
            doc_type = "hybrid"
            confidence = 0.90
            
        return PdfClassificationResult(
            document_type=doc_type,
            confidence=confidence,
            pages=pages_count,
            text_pages=text_pages,
            image_pages=image_pages,
            details={
                "message": "Classified using PyMuPDF text and image presence heuristics."
            }
        )
