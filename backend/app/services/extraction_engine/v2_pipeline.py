import os
import cv2
import logging
from app.services.extraction_engine.models.document import StructuredDocument, DocumentPage, DocumentBlock, OcrElement
from app.services.extraction_engine.pdf_classifier import PdfClassifier
from app.services.extraction_engine.image_preprocessor import ImagePreprocessor
from app.services.extraction_engine.ocr_engine import HybridOcrEngine
from app.services.extraction_engine.layout_analyzer import LayoutAnalyzer
from app.services.extraction_engine.header_footer_detector import HeaderFooterDetector
from app.services.extraction_engine.table_detector import TableDetector
from app.services.extraction_engine.semantic_section_parser import SemanticSectionParser
from app.services.extraction_engine.contract_entities import ContractEntityExtractor
from app.services.extraction_engine.ocr_evaluator import OcrEvaluator

logger = logging.getLogger(__name__)

class OCRV2Pipeline:
    def __init__(self):
        self.classifier = PdfClassifier()
        from app.core.config import settings
        self.preprocessor = ImagePreprocessor(base_output_dir=os.path.join(settings.UPLOADS_DIR, "processed"))
        self.ocr_engine = HybridOcrEngine()
        self.layout_analyzer = LayoutAnalyzer()
        self.hf_detector = HeaderFooterDetector()
        self.table_detector = TableDetector()
        self.semantic_parser = SemanticSectionParser()
        self.entity_extractor = ContractEntityExtractor()
        self.evaluator = OcrEvaluator()

    def process_document(self, pdf_path: str) -> StructuredDocument:
        logger.info(f"Starting OCR V2 Pipeline for {pdf_path}")
        doc = StructuredDocument()

        # 1. Classification
        cls_result = self.classifier.classify(pdf_path)
        doc.metadata["document_type"] = cls_result.document_type

        # 2. Preprocessing images
        img_result = self.preprocessor.process("doc", pdf_path)
        processed_images = img_result["processed_images"]
        original_images = img_result.get("original_images", processed_images)

        # We need fitz to extract native words if needed
        import fitz
        fitz_doc = fitz.open(pdf_path)

        # 3. OCR & Layout
        doc_blocks = []
        for i, img_path in enumerate(processed_images):
            page_num = i + 1
            
            page_cls = next((p for p in getattr(cls_result, "page_results", []) if p.page_number == page_num), None)

            if page_cls:
                needs_ocr = page_cls.needs_ocr
            else:
                needs_ocr = (getattr(cls_result, "document_type", "scanned") == "scanned")

            if needs_ocr:
                image = cv2.imread(processed_images[i])
            else:
                image = cv2.imread(original_images[i])

            target_height, target_width = image.shape[:2]

            page_source = "ocr_v2"

            if not needs_ocr:
                fitz_page = fitz_doc[i]
                mat = fitz_page.rotation_matrix
                pdf_width = fitz_page.rect.width
                pdf_height = fitz_page.rect.height

                scale_x = target_width / pdf_width if pdf_width else 1.0
                scale_y = target_height / pdf_height if pdf_height else 1.0

                elements = []
                words = fitz_page.get_text("words")
                if isinstance(words, str):
                    words = [] # Handle bad test mocks
                for w in words:
                    if len(w) < 8:
                        continue
                    x0, y0, x1, y1, text, block_no, line_no, word_no = w[:8]
                    raw_rect = fitz.Rect(w[:4])
                    visual_rect = raw_rect * mat

                    nx0 = max(0.0, min(visual_rect.x0 * scale_x, float(target_width)))
                    ny0 = max(0.0, min(visual_rect.y0 * scale_y, float(target_height)))
                    nx1 = max(0.0, min(visual_rect.x1 * scale_x, float(target_width)))
                    ny1 = max(0.0, min(visual_rect.y1 * scale_y, float(target_height)))
                    if nx0 >= nx1 or ny0 >= ny1:
                        continue

                    elements.append(OcrElement(
                        text=text,
                        confidence=1.0,
                        x=nx0,
                        y=ny0,
                        width=nx1 - nx0,
                        height=ny1 - ny0,
                        page_number=page_num,
                        source="native"
                    ))
            else:
                ocr_result = self.ocr_engine.extract(image, page_number=page_num)
                elements = ocr_result["elements"]
                if elements:
                    page_source = getattr(elements[0], "source", "paddleocr")

            doc.pages.append(DocumentPage(
                page_number=page_num,
                width=float(target_width),
                height=float(target_height),
                elements=elements
            ))

            layout_result = self.layout_analyzer.analyze(elements)
            for b in layout_result["blocks"]:
                doc_blocks.append(DocumentBlock(
                    type=b.get("type", "paragraph"),
                    original_text=b.get("text", ""),
                    content=b.get("text", ""),
                    confidence=b.get("confidence", 0.0),
                    page=page_num,
                    bounding_box=b["bounding_box"],
                    style=b.get("style", {}),
                    source=page_source
                ))

        doc.blocks = doc_blocks
        fitz_doc.close()

        # 4. Header/Footer Detection
        doc = self.hf_detector.process(doc)

        # 5. Table Detection
        doc = self.table_detector.process(doc, pdf_path)

        # 6. Semantic Section Parsing
        doc = self.semantic_parser.process(doc)

        # 7. Contract Entity Extraction
        doc = self.entity_extractor.process(doc)

        # 8. Evaluation
        eval_result = self.evaluator.evaluate(doc)
        doc.metadata["evaluation"] = eval_result
        doc.confidence = eval_result.get("score", 0.0)

        return doc
