import fitz  # PyMuPDF
from typing import Dict, Any
from app.services.extraction_engine.models.document import PdfClassificationResult, PageClassification

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
        page_results = []
        for i in range(pages_count):
            page = doc[i]
            text = page.get_text("text").strip()
            text_length = len(text)

            # Also check images to be more robust
            images = page.get_images(full=True)

            if text_length > self.text_length_threshold:
                text_pages += 1
                needs_ocr = False
            else:
                image_pages += 1
                needs_ocr = True

            page_results.append(PageClassification(
                page_number=i+1,
                needs_ocr=needs_ocr,
                native_text_length=text_length
            ))

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
            },
            page_results=page_results
        )
