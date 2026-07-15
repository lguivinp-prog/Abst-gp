import fitz
import pdfplumber
import cv2
import numpy as np
from typing import List, Dict, Any, Tuple
from app.services.extraction_engine.models.document import StructuredDocument, TableBlock, OcrElement
from app.services.extraction_engine.config import table_config

class TableDetector:
    def process(self, document: StructuredDocument, pdf_path: str) -> StructuredDocument:
        doc_type = document.metadata.get("document_type", "scanned")
        
        new_tables = []
        try:
            pdf_document = fitz.open(pdf_path)
        except Exception:
            pdf_document = None
        
        for i, page in enumerate(document.pages):
            page_num = i + 1
            tables_found = []
            
            if doc_type == "digital":
                tables_found = self._extract_digital(pdf_path, page_num, page)
                if not tables_found and pdf_document:
                    tables_found = self._extract_scanned(pdf_document, page_num, page)
            else:
                if pdf_document:
                    tables_found = self._extract_scanned(pdf_document, page_num, page)
                
            new_tables.extend(tables_found)
            
        document.tables = new_tables
        return document
        
    def _extract_digital(self, pdf_path: str, page_num: int, page_obj) -> List[TableBlock]:
        tables = []
        try:
            with pdfplumber.open(pdf_path) as pdf:
                page = pdf.pages[page_num - 1]
                plumber_tables = page.extract_tables()
                for table in plumber_tables:
                    if not table or len(table) < 2:
                        continue
                    non_empty = [cell for row in table for cell in row if cell and str(cell).strip()]
                    if not non_empty:
                        continue
                        
                    columns = [str(c).strip() if c else "" for c in table[0]]
                    rows = [[str(c).strip() if c else "" for c in row] for row in table[1:]]
                    
                    tb = TableBlock(
                        columns=columns,
                        rows=rows,
                        page_number=page_num,
                        confidence=table_config.MIN_TABLE_CONFIDENCE,
                        extraction_method="pdfplumber",
                        bounding_box={},
                        elements_used=[]
                    )
                    tables.append(tb)
        except Exception:
            pass
        return tables
        
    def _extract_scanned(self, pdf_document, page_num: int, page_obj) -> List[TableBlock]:
        try:
            page = pdf_document[page_num - 1]
            pix = page.get_pixmap()
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
            if pix.n == 4:
                img = cv2.cvtColor(img, cv2.COLOR_RGBA2RGB)
                
            opencv_tables = self._detect_with_opencv(img, page_obj)
            if opencv_tables:
                return opencv_tables
        except Exception:
            pass
            
        return self._detect_with_clustering(page_obj)
        
    def _detect_with_opencv(self, img, page_obj) -> List[TableBlock]:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        thresh, bin_img = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)
        
        kernel_h = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
        detect_h = cv2.morphologyEx(bin_img, cv2.MORPH_OPEN, kernel_h, iterations=2)
        
        kernel_v = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 40))
        detect_v = cv2.morphologyEx(bin_img, cv2.MORPH_OPEN, kernel_v, iterations=2)
        
        table_mask = cv2.addWeighted(detect_h, 0.5, detect_v, 0.5, 0.0)
        _, table_mask = cv2.threshold(table_mask, 50, 255, cv2.THRESH_BINARY)
        
        contours, _ = cv2.findContours(table_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        tables = []
        for c in contours:
            x, y, w, h = cv2.boundingRect(c)
            if w > table_config.MIN_TABLE_WIDTH and h > table_config.MIN_TABLE_HEIGHT:
                table_elements = [e for e in page_obj.elements if e.x >= x and e.y >= y and e.x + e.width <= x + w and e.y + e.height <= y + h]
                
                if len(table_elements) > 4:
                    tb = self._cluster_elements(table_elements, page_obj.page_number, "opencv", {"x": float(x), "y": float(y), "w": float(w), "h": float(h)})
                    if tb.rows:
                        tables.append(tb)
                    
        return tables
        
    def _detect_with_clustering(self, page_obj) -> List[TableBlock]:
        elements = page_obj.elements
        if not elements:
            return []
            
        elements_sorted = sorted(elements, key=lambda e: e.y)
        lines = []
        current_line = []
        current_y = None
        for e in elements_sorted:
            if current_y is None:
                current_y = e.y
                current_line.append(e)
            else:
                if abs(e.y - current_y) < table_config.TABLE_Y_THRESHOLD: 
                    current_line.append(e)
                else:
                    lines.append(current_line)
                    current_line = [e]
                    current_y = e.y
        if current_line:
            lines.append(current_line)
            
        tabular_lines = []
        for line in lines:
            line.sort(key=lambda e: e.x)
            if len(line) >= 2:
                tabular_lines.append(line)
                
        tables = []
        current_table = []
        for i, line in enumerate(tabular_lines):
            if not current_table:
                current_table.append(line)
            else:
                prev_line = current_table[-1]
                avg_y_prev = sum(e.y for e in prev_line) / len(prev_line)
                avg_y_curr = sum(e.y for e in line) / len(line)
                
                if avg_y_curr - avg_y_prev < table_config.CONSECUTIVE_LINE_Y_GAP: 
                    current_table.append(line)
                else:
                    if len(current_table) > 1:
                        tables.append(current_table)
                    current_table = [line]
                    
        if len(current_table) > 1:
            tables.append(current_table)
            
        result_tables = []
        for table_lines in tables:
            table_elems = [e for line in table_lines for e in line]
            min_x = min(e.x for e in table_elems)
            min_y = min(e.y for e in table_elems)
            max_x = max(e.x + e.width for e in table_elems)
            max_y = max(e.y + e.height for e in table_elems)
            bbox = {"x": min_x, "y": min_y, "w": max_x - min_x, "h": max_y - min_y}
            
            tb = self._cluster_elements(table_elems, page_obj.page_number, "ocr_cluster", bbox)
            if len(tb.rows) > 0:
                result_tables.append(tb)
                
        return result_tables
        
    def _cluster_elements(self, elements: List[OcrElement], page_number: int, method: str, bbox: Dict[str, float]) -> TableBlock:
        rows = []
        elements_sorted = sorted(elements, key=lambda e: e.y)
        
        current_row = []
        current_y = None
        for e in elements_sorted:
            if current_y is None:
                current_y = e.y
                current_row.append(e)
            else:
                if abs(e.y - current_y) < table_config.TABLE_Y_THRESHOLD: 
                    current_row.append(e)
                else:
                    rows.append(current_row)
                    current_row = [e]
                    current_y = e.y
        if current_row:
            rows.append(current_row)
            
        processed_rows = []
        for row in rows:
            row.sort(key=lambda e: e.x)
            processed_rows.append([e.text for e in row])
            
        if not processed_rows or len(processed_rows) < 2:
            return TableBlock(columns=[], rows=[], page_number=page_number, confidence=0.0, extraction_method=method, bounding_box=bbox, elements_used=elements)
            
        columns = processed_rows[0]
        data_rows = processed_rows[1:]
        
        return TableBlock(
            columns=columns,
            rows=data_rows,
            page_number=page_number,
            confidence=table_config.MIN_TABLE_CONFIDENCE if method == "ocr_cluster" else 0.95,
            extraction_method=method,
            bounding_box=bbox,
            elements_used=elements
        )
