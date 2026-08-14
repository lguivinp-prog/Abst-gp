import os
import tempfile
import fitz  # PyMuPDF
from pydantic import BaseModel
from typing import List, Optional
from app.models.v6.ocr import StructuredPage, StructuredBlock, BBox, StructuredTable, StructuredRow, StructuredCell, StructuredDocument

class OCRExtractionResult(BaseModel):
    text: str
    pages_text: List[str]
    page_count: int
    ocr_used: bool
    language: str
    confidence_avg: float
    errors: List[str]
    structured_document: Optional[StructuredDocument] = None

def _extract_page_structure(page, page_num: int, source_type: str, pdf_path: str = None) -> StructuredPage:
    rect = page.rect
    width, height = rect.width, rect.height
    clip_rect = fitz.Rect(rect.x0, rect.y0 + rect.height * 0.10, rect.x1, rect.y1 - rect.height * 0.10)
    
    blocks_data = []
    table_bboxes = []
    
    def process_tables(found_tables, from_pdfplumber=False):
        valid = False
        tables_to_iterate = found_tables if from_pdfplumber else (found_tables.tables if hasattr(found_tables, 'tables') else [])
        
        if tables_to_iterate and len(tables_to_iterate) > 0:
            for t_idx, table in enumerate(tables_to_iterate):
                # For pdfplumber, table is a Table object. For PyMuPDF, table is a Table object.
                if from_pdfplumber:
                    bbox = table.bbox
                    t_rect = fitz.Rect(bbox)
                else:
                    bbox = table.bbox
                    t_rect = fitz.Rect(bbox)
                
                ratio = t_rect.get_area() / clip_rect.get_area()
                
                if ratio > 0.8:
                    continue
                    
                table_bboxes.append(t_rect)
                valid = True
                
                if from_pdfplumber:
                    sub_tables = []
                    current_sub = []
                    prev_y1 = None
                    
                    for row_obj in table.rows:
                        row_cells = row_obj.cells
                        y0, y1 = row_obj.bbox[1], row_obj.bbox[3]
                        
                        non_empty_cells = [c for c in row_cells if c and str(c).strip()]
                        
                        if prev_y1 is not None:
                            distance = y0 - prev_y1
                            # Use 8.0 points as the threshold to separate tables
                            if distance > 8.0:
                                if len(current_sub) >= 2:
                                    sub_tables.append(current_sub)
                                current_sub = []
                        prev_y1 = y1
                        
                        if len(non_empty_cells) >= 3:
                            current_sub.append((row_cells, row_obj.bbox))
                        else:
                            if len(current_sub) >= 2:
                                sub_tables.append(current_sub)
                            current_sub = []
                            
                    if len(current_sub) >= 2:
                        sub_tables.append(current_sub)
                        
                    for sub_t_data in sub_tables:
                        row_count = len(sub_t_data)
                        col_count_orig = len(sub_t_data[0][0]) if row_count > 0 else 0
                        
                        if row_count > 100 or col_count_orig > 30 or (row_count <= 1):
                            continue
                            
                        valid_cols = []
                        for c_idx in range(col_count_orig):
                            col_has_data = any(sub_t_data[r_idx][0][c_idx] and str(sub_t_data[r_idx][0][c_idx]).strip() for r_idx in range(row_count))
                            if col_has_data:
                                valid_cols.append(c_idx)
                                
                        if not valid_cols:
                            continue
                            
                        true_col_count = len(valid_cols)
                        
                        rows_data = []
                        min_x0, min_y0, max_x1, max_y1 = float("inf"), float("inf"), float("-inf"), float("-inf")
                        
                        for row_cells, row_bbox in sub_t_data:
                            cells_data = []
                            for c_idx in valid_cols:
                                cell_val = row_cells[c_idx] if c_idx < len(row_cells) else ""
                                text = str(cell_val).replace("\n", " ").strip() if cell_val else ""
                                cells_data.append(StructuredCell(text=text, bbox=None))
                            rows_data.append(StructuredRow(cells=cells_data))
                            
                            if row_bbox:
                                min_x0 = min(min_x0, row_bbox[0])
                                min_y0 = min(min_y0, row_bbox[1])
                                max_x1 = max(max_x1, row_bbox[2])
                                max_y1 = max(max_y1, row_bbox[3])
                                
                        if min_x0 != float("inf"):
                            b_box = BBox(x0=min_x0, y0=min_y0, x1=max_x1, y1=max_y1)
                        else:
                            b_box = BBox(x0=bbox[0], y0=bbox[1], x1=bbox[2], y1=bbox[3])
                            
                        struct_table = StructuredTable(
                            rows=rows_data,
                            row_count=row_count,
                            col_count=true_col_count,
                            bbox=b_box
                        )
                        
                        blocks_data.append(StructuredBlock(
                            type="TABLE",
                            page_num=page_num,
                            reading_order=0,
                            bbox=struct_table.bbox,
                            table_data=struct_table,
                            source_method="ocr_tables" if source_type == "scanned" else "native"
                        ))
                else:
                    row_count = len(table.cells)
                    col_count = len(table.cells[0]) if row_count > 0 else 0
                    if row_count <= 1 and col_count <= 1:
                        continue
                    if row_count > 100 or col_count > 30:
                        continue
                    
                    rows_data = []
                    for row in table.cells:
                        cells_data = []
                        for cell in row:
                            cell_text = ""
                            if cell and isinstance(cell, tuple) and len(cell) == 4:
                                c_rect = fitz.Rect(cell)
                                cell_text = page.get_text("text", clip=c_rect).strip()
                                c_bbox = BBox(x0=c_rect.x0, y0=c_rect.y0, x1=c_rect.x1, y1=c_rect.y1)
                            else:
                                c_bbox = None
                            cell_text = cell_text.replace("\n", " ").strip()
                            cells_data.append(StructuredCell(text=cell_text, bbox=c_bbox))
                        rows_data.append(StructuredRow(cells=cells_data))
                        
                    struct_table = StructuredTable(
                        rows=rows_data,
                        row_count=row_count,
                        col_count=col_count,
                        bbox=BBox(x0=bbox[0], y0=bbox[1], x1=bbox[2], y1=bbox[3])
                    )
                    
                    blocks_data.append(StructuredBlock(
                        type="TABLE",
                        page_num=page_num,
                        reading_order=0,
                        bbox=struct_table.bbox,
                        table_data=struct_table,
                        source_method="native"
                    ))
        return valid

    tables_found = False
    if source_type == "scanned" and pdf_path:
        try:
            import pdfplumber
            with pdfplumber.open(pdf_path) as pdf:
                p_page = pdf.pages[page_num - 1]
                crop_box = (0, p_page.height * 0.1, p_page.width, p_page.height * 0.9)
                cropped_page = p_page.crop(crop_box)
                found_tables = cropped_page.find_tables({"vertical_strategy": "text", "horizontal_strategy": "text", "intersection_y_tolerance": 3})
                if found_tables:
                    tables_found = process_tables(found_tables, from_pdfplumber=True)
        except Exception as e:
            pass

    if not tables_found:
        tables = page.find_tables(clip=clip_rect, strategy="lines_strict")
        if not process_tables(tables):
            tables_text = page.find_tables(clip=clip_rect, strategy="text")
            process_tables(tables_text)
        
    text_blocks = page.get_text("blocks", clip=clip_rect)
    for b in text_blocks:
        x0, y0, x1, y1, text, block_no, block_type = b
        b_rect = fitz.Rect(x0, y0, x1, y1)
        
        if block_type != 0:
            continue
            
        text = text.strip()
        if not text:
            continue
            
        is_in_table = False
        for t_rect in table_bboxes:
            intersect = b_rect.intersect(t_rect)
            if intersect.get_area() > 0.5 * b_rect.get_area():
                is_in_table = True
                break
                
        if is_in_table:
            continue
            
        blocks_data.append(StructuredBlock(
            type="PARAGRAPH",
            text=text,
            page_num=page_num,
            reading_order=0,
            bbox=BBox(x0=x0, y0=y0, x1=x1, y1=y1),
            source_method="ocr_blocks" if source_type == "scanned" else "native"
        ))
        
    blocks_data.sort(key=lambda b: (b.bbox.y0 if b.bbox else 0, b.bbox.x0 if b.bbox else 0))
    for i, b in enumerate(blocks_data):
        b.reading_order = i + 1
        
    return StructuredPage(
        page_num=page_num,
        blocks=blocks_data,
        width=width,
        height=height,
        source_type=source_type
    )

def process_pdf(file_path: str, force_ocr: bool = False, language: str = "spa") -> OCRExtractionResult:
    errors = []
    text_content = ""
    pages_text = []
    structured_pages = []
    page_count = 0
    ocr_used = False
    
    try:
        doc = fitz.open(file_path)
        page_count = len(doc)
        
        if not force_ocr:
            for i, page in enumerate(doc):
                page_str = page.get_text("text").strip()
                if len(page_str) > 50:
                    sp = _extract_page_structure(page, i + 1, "digital", file_path)
                    structured_pages.append(sp)
                    p_text = "\n\n".join([b.text for b in sp.blocks if b.type != "TABLE" and b.text])
                    pages_text.append(p_text)
                    text_content += p_text + "\n\n"
                else:
                    pages_text.append("")
                    structured_pages.append(None)
                    
        doc.close()
        
        if force_ocr or (len(text_content.strip()) < page_count * 50):
            try:
                import ocrmypdf
                from ocrmypdf.exceptions import MissingDependencyError
                
                ocr_used = True
                text_content = "" 
                pages_text = []
                structured_pages = []
                
                with tempfile.TemporaryDirectory() as temp_dir:
                    out_pdf = os.path.join(temp_dir, "ocr_output.pdf")
                    
                    ocrmypdf.ocr(
                        file_path, 
                        out_pdf, 
                        language=language,
                        force_ocr=True,
                        output_type="pdf",
                        optimize=0,
                        progress_bar=False
                    )
                    
                    doc_ocr = fitz.open(out_pdf)
                    for i, page in enumerate(doc_ocr):
                        sp = _extract_page_structure(page, i + 1, "scanned", out_pdf)
                        structured_pages.append(sp)
                        
                        legacy_page_text = ""
                        for b in sp.blocks:
                            if b.type == "TABLE" and b.table_data:
                                for row in b.table_data.rows:
                                    row_str = " | ".join([c.text for c in row.cells])
                                    legacy_page_text += row_str + "\n"
                                legacy_page_text += "\n"
                            elif b.text:
                                legacy_page_text += b.text + "\n\n"
                                
                        pages_text.append(legacy_page_text)
                        text_content += legacy_page_text + "\n\n"
                        
                    doc_ocr.close()
            except Exception as ocr_e:
                print(f"Skipping OCR fallback: {ocr_e}")
                ocr_used = False
                doc = fitz.open(file_path)
                structured_pages = []
                pages_text = []
                text_content = ""
                for i, page in enumerate(doc):
                    page_str = page.get_text("text").strip()
                    if len(page_str) > 0:
                        sp = _extract_page_structure(page, i + 1, "digital", file_path)
                        structured_pages.append(sp)
                        p_text = "\n\n".join([b.text for b in sp.blocks if b.type != "TABLE" and b.text])
                        pages_text.append(p_text)
                        text_content += p_text + "\n\n"
                    else:
                        pages_text.append("")
                        structured_pages.append(None)
                doc.close()
        
        final_pages = [p for p in structured_pages if p is not None]
        
        structured_doc = StructuredDocument(
            schema_version=1,
            pages=final_pages,
            metadata={
                "ocr_used": ocr_used,
                "language": language
            }
        )
                
    except Exception as e:
        import traceback
        errors.append(f"Error procesando el PDF: {str(e)}\n{traceback.format_exc()}")
        structured_doc = None

    return OCRExtractionResult(
        text=text_content,
        pages_text=pages_text,
        page_count=page_count,
        ocr_used=ocr_used,
        language=language if ocr_used else 'N/A',
        confidence_avg=0.85 if ocr_used else 1.0,
        errors=errors,
        structured_document=structured_doc
    )
