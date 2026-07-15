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
                        "data": tab.extract()
                    })
        doc.close()
    except Exception as e:
        print(f"Error extrayendo tablas: {e}")
        
    return tables_data
