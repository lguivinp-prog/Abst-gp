import os
import tempfile
import fitz  # PyMuPDF
import ocrmypdf
from pydantic import BaseModel
from typing import List, Optional

class OCRExtractionResult(BaseModel):
    text: str
    pages_text: List[str]
    page_count: int
    ocr_used: bool
    language: str
    confidence_avg: float
    errors: List[str]

def process_pdf(file_path: str, force_ocr: bool = False, language: str = 'spa') -> OCRExtractionResult:
    """
    Procesa un PDF. Si no tiene texto, le aplica OCR (usando ocrmypdf).
    Retorna el texto extraído, texto por páginas y metadatos.
    """
    errors = []
    text_content = ""
    pages_text = []
    page_count = 0
    ocr_used = False
    
    try:
        # Abrir con PyMuPDF para revisar si tiene texto embebido
        doc = fitz.open(file_path)
        page_count = len(doc)
        
        if not force_ocr:
            for page in doc:
                rect = page.rect
                # Ignorar el 12% superior y 10% inferior para saltar encabezados, sellos, membretes y números de página
                clip_rect = fitz.Rect(rect.x0, rect.y0 + rect.height * 0.12, rect.x1, rect.y1 - rect.height * 0.10)
                page_str = page.get_text("text", clip=clip_rect)
                pages_text.append(page_str)
                text_content += page_str + "\n"
                
        doc.close()
        
        # Heurística simple: si tiene muy pocos caracteres por página en promedio, asumimos que es imagen
        if force_ocr or (len(text_content.strip()) < page_count * 50):
            ocr_used = True
            text_content = "" # Resetear texto
            pages_text = []
            
            with tempfile.TemporaryDirectory() as temp_dir:
                out_pdf = os.path.join(temp_dir, "ocr_output.pdf")
                
                # Configurar OCRmyPDF para optimizar texto
                ocrmypdf.ocr(
                    file_path, 
                    out_pdf, 
                    language=language,
                    force_ocr=True,
                    output_type='pdf',
                    optimize=0,  # Optimización rápida
                    progress_bar=False
                )
                
                # Extraer texto del nuevo PDF generado con OCR
                doc_ocr = fitz.open(out_pdf)
                for page in doc_ocr:
                    rect = page.rect
                    clip_rect = fitz.Rect(rect.x0, rect.y0 + rect.height * 0.12, rect.x1, rect.y1 - rect.height * 0.10)
                    page_str = page.get_text("text", clip=clip_rect)
                    pages_text.append(page_str)
                    text_content += page_str + "\n"
                doc_ocr.close()
                
    except Exception as e:
        errors.append(f"Error procesando el PDF: {str(e)}")

    return OCRExtractionResult(
        text=text_content,
        pages_text=pages_text,
        page_count=page_count,
        ocr_used=ocr_used,
        language=language if ocr_used else 'N/A',
        confidence_avg=0.85 if ocr_used else 1.0, # OCRmyPDF no exporta fácilmente la confianza por palabra en Python, asignamos un proxy o requeriríamos analizar hOCR
        errors=errors
    )
