import fitz
from typing import List, Dict, Any

def extract_tables_from_pdf(pdf_path: str) -> List[Dict[str, Any]]:
    """
    Extrae tablas de un PDF digital utilizando PyMuPDF.
    Devuelve las tablas en un formato estructurado.
    """
    tables_data = []
    try:
        doc = fitz.open(pdf_path)
        for page_num, page in enumerate(doc):
            # En versiones recientes de PyMuPDF: page.find_tables()
            # Este es un acercamiento simplificado
            tabs = page.find_tables()
            if tabs:
                for tab in tabs:
                    tables_data.append({
                        "page": page_num + 1,
                        "data": tab.extract(),
                        "source": "native"
                    })
            else:
                # Layout separation: use grid_detector for non-native tables (OCR pipeline)
                from app.services.ocr.grid_detector import extract_tables_by_dark_header, extract_tables_by_grid_page
                
                # First try dark headers
                ocr_tabs = extract_tables_by_dark_header(page, page_num)
                if not ocr_tabs:
                    # Fallback to grid lines
                    ocr_tabs = extract_tables_by_grid_page(page, page_num)
                
                for tab in ocr_tabs:
                    tables_data.append({
                        "page": page_num + 1,
                        "data": tab.extract(),
                        "source": "ocr_layout"
                    })
                    
        doc.close()
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error extrayendo tablas")
        
    return tables_data
