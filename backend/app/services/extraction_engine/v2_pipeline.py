import os
import cv2
import logging
from app.services.extraction_engine.models.document import StructuredDocument, DocumentPage, DocumentBlock
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
        
        # 3. OCR & Layout
        doc_blocks = []
        for i, img_path in enumerate(processed_images):
            page_num = i + 1
            image = cv2.imread(img_path)
            ocr_result = self.ocr_engine.extract(image, page_number=page_num)
            elements = ocr_result["elements"]
            
            doc.pages.append(DocumentPage(
                page_number=page_num,
                width=float(image.shape[1]),
                height=float(image.shape[0]),
                elements=elements
            ))
            
            layout_result = self.layout_analyzer.analyze(elements)
            for b in layout_result["blocks"]:
                doc_blocks.append(DocumentBlock(
                    type=b["type"],
                    content=b["text"],
                    page=page_num,
                    bounding_box=b["bounding_box"],
                    style=b.get("style", {})
                ))
                
        doc.blocks = doc_blocks
        
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
