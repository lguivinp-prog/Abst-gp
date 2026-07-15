import time
import numpy as np
from abc import ABC, abstractmethod
from typing import List, Dict, Any
import logging

from app.services.extraction_engine.models.document import OcrElement

logger = logging.getLogger(__name__)

class BaseOcrEngine(ABC):
    @abstractmethod
    def extract(self, page_image: np.ndarray, page_number: int) -> Dict[str, Any]:
        """
        Returns a dict containing:
        - elements: List[OcrElement]
        - stats: Dict (time, memory, etc.)
        """
        pass

class PaddleOCREngine(BaseOcrEngine):
    def __init__(self):
        # We initialize it only when needed to avoid huge memory footprint if unused
        from paddleocr import PaddleOCR
        # Configure for Spanish, CPU, and orientation detection
        self.ocr = PaddleOCR(use_angle_cls=True, lang='es', use_gpu=False, show_log=False)

    def extract(self, page_image: np.ndarray, page_number: int) -> Dict[str, Any]:
        start_time = time.time()
        
        # result is a list of lines: [[[[x1,y1],[x2,y2],[x3,y3],[x4,y4]], ("text", confidence)], ...]
        results = self.ocr.ocr(page_image, cls=True)
        
        elements = []
        if results and results[0]:
            for line in results[0]:
                box, (text, confidence) = line
                
                # box is a list of 4 points: [top_left, top_right, bottom_right, bottom_left]
                xs = [pt[0] for pt in box]
                ys = [pt[1] for pt in box]
                x = min(xs)
                y = min(ys)
                width = max(xs) - x
                height = max(ys) - y
                
                element = OcrElement(
                    text=text,
                    confidence=float(confidence),
                    x=float(x),
                    y=float(y),
                    width=float(width),
                    height=float(height),
                    page_number=page_number,
                    source="paddleocr"
                )
                elements.append(element)
                
        duration = time.time() - start_time
        return {
            "elements": elements,
            "stats": {
                "engine": "paddleocr",
                "time_seconds": duration,
                "elements_count": len(elements)
            }
        }

class TesseractEngine(BaseOcrEngine):
    def extract(self, page_image: np.ndarray, page_number: int) -> Dict[str, Any]:
        import pytesseract
        from pytesseract import Output
        
        start_time = time.time()
        
        # Output as dict gives level, page_num, block_num, par_num, line_num, word_num, left, top, width, height, conf, text
        data = pytesseract.image_to_data(page_image, lang='spa', output_type=Output.DICT)
        
        elements = []
        n_boxes = len(data['text'])
        for i in range(n_boxes):
            text = data['text'][i].strip()
            conf = int(data['conf'][i])
            
            if text and conf > 0: # -1 means no text/block separator
                element = OcrElement(
                    text=text,
                    confidence=float(conf) / 100.0,
                    x=float(data['left'][i]),
                    y=float(data['top'][i]),
                    width=float(data['width'][i]),
                    height=float(data['height'][i]),
                    page_number=page_number,
                    source="tesseract"
                )
                elements.append(element)
                
        duration = time.time() - start_time
        return {
            "elements": elements,
            "stats": {
                "engine": "tesseract",
                "time_seconds": duration,
                "elements_count": len(elements)
            }
        }

class HybridOcrEngine:
    def __init__(self, fallback_confidence: float = 0.60):
        self.primary_engine = PaddleOCREngine()
        self.fallback_engine = TesseractEngine()
        self.fallback_confidence = fallback_confidence

    def extract(self, page_image: np.ndarray, page_number: int) -> Dict[str, Any]:
        result = self.primary_engine.extract(page_image, page_number)
        
        # Calculate average confidence
        elements = result["elements"]
        
        if not elements:
            # If nothing found, try fallback
            fallback_result = self.fallback_engine.extract(page_image, page_number)
            return fallback_result
            
        avg_confidence = sum(e.confidence for e in elements) / len(elements)
        
        if avg_confidence < self.fallback_confidence:
            logger.warning(f"Low confidence ({avg_confidence:.2f}) from PaddleOCR on page {page_number}. Falling back to Tesseract.")
            fallback_result = self.fallback_engine.extract(page_image, page_number)
            
            fallback_elements = fallback_result["elements"]
            if fallback_elements:
                fb_avg = sum(e.confidence for e in fallback_elements) / len(fallback_elements)
                if fb_avg > avg_confidence:
                    return fallback_result
        
        return result
