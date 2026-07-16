import os
import cv2
import json
from app.services.extraction_engine.models.document import StructuredDocument, DocumentPage, DocumentBlock, OcrElement
from app.services.extraction_engine.image_preprocessor import ImagePreprocessor
from app.services.extraction_engine.ocr_engine import HybridOcrEngine
from app.services.extraction_engine.layout_analyzer import LayoutAnalyzer
from app.services.extraction_engine.header_footer_detector import HeaderFooterDetector
from app.services.extraction_engine.table_detector import TableDetector
from app.services.extraction_engine.semantic_section_parser import SemanticSectionParser
from app.services.extraction_engine.contract_entities import ContractEntityExtractor
from app.services.extraction_engine.pdf_classifier import PdfClassifier

def run_phase4():
    pdf_path = "/data/uploads/0fc2be49-e700-4383-940b-08e6e6cc2d31.pdf"
    if not os.path.exists(pdf_path):
        print("PDF not found!")
        return

    print("1. Classification...")
    classifier = PdfClassifier()
    clf_result = classifier.classify(pdf_path)
    
    print("2. Preprocessing images...")
    preprocessor = ImagePreprocessor(base_output_dir="/data/processed")
    img_result = preprocessor.process("doc_phase4", pdf_path)
    processed_images = img_result["processed_images"]
    
    print("3. OCR & Layout...")
    ocr = HybridOcrEngine()
    layout = LayoutAnalyzer()
    
    doc_pages = []
    doc_blocks = []
    
    for page_idx in range(len(processed_images)):
        print(f"   Procesando Página {page_idx + 1}...")
        img_path = processed_images[page_idx]
        image = cv2.imread(img_path)
        
        ocr_result = ocr.extract(image, page_number=page_idx + 1)
        elements = ocr_result["elements"]
        
        doc_page = DocumentPage(
            page_number=page_idx + 1,
            width=float(image.shape[1]),
            height=float(image.shape[0]),
            elements=elements
        )
        doc_pages.append(doc_page)
        
        layout_result = layout.analyze(elements)
        blocks = layout_result["blocks"]
        
        for b in blocks:
            doc_blocks.append(DocumentBlock(
                type=b["type"],
                content=b["text"],
                page=page_idx + 1,
                bounding_box=b["bounding_box"],
                style=b.get("style", {})
            ))
            
    document = StructuredDocument(
        metadata={"document_type": clf_result.document_type},
        pages=doc_pages,
        blocks=doc_blocks
    )
    
    print("4. Header/Footer Detection...")
    hfd = HeaderFooterDetector()
    document = hfd.process(document)
    
    print("5. Table Detection...")
    td = TableDetector()
    document = td.process(document, pdf_path)
    
    print("6. Semantic Section Parsing...")
    ssp = SemanticSectionParser()
    document = ssp.process(document)
    
    print("7. Contract Entity Extraction...")
    cee = ContractEntityExtractor()
    document = cee.process(document)
    
    print("\n================ OCR V2 PHASE 4 REPORT ================")
    
    print("\n--- TEXTOS CON POSIBLES ENTIDADES ---")
    for b in document.blocks:
        if isinstance(b.content, str):
            text = b.content.lower()
            if any(k in text for k in ["plazo", "días", "dias", "garant", "pago", "entrega"]):
                print(f"[PAGE {b.page}] {b.content}")
    
    print(f"\nTablas detectadas:\n{len(document.tables)}")
    
    methods = {"pdfplumber": 0, "opencv": 0, "ocr_cluster": 0}
    for t in document.tables:
        if t.extraction_method in methods:
            methods[t.extraction_method] += 1
            
    print("\nMétodo:")
    for method, count in methods.items():
        print(f"{method}:\n{count}")
        
    sections = [b for b in document.blocks if b.type == "section"]
    print(f"\nSecciones detectadas:\n{len(sections)}/{len(ssp.known_sections)}")
    
    plazos = [e for e in document.entities if e.type == "delivery_term"]
    garantias = [e for e in document.entities if e.type == "warranty"]
    pagos = [e for e in document.entities if e.type == "payment_condition"]
    
    print("\nEntidades contractuales:")
    print(f"Plazo:\n{len(plazos)}")
    print(f"Garantía:\n{len(garantias)}")
    print(f"Pago:\n{len(pagos)}")
    
    print("\nErrores:\nNinguno reportado.")
    print("========================================================\n")
    
    print("\n--- VALIDACIÓN PÁGINA 3 (TABLAS) ---")
    page3_tables = [t for t in document.tables if t.page_number == 3]
    for i, t in enumerate(page3_tables):
        print(f"Tabla {i+1} ({t.extraction_method}):")
        print(f"Columnas: {t.columns}")
        for r in t.rows[:2]:
            print(f"Fila: {r}")
            
    print("\n--- VALIDACIÓN SECCIONES CONTRACTUALES ---")
    for s in sections:
        print(f"[SECCIÓN] {s.normalized_text} (Pág {s.page})")
        
    print("\n--- VALIDACIÓN ENTIDADES ---")
    for e in document.entities:
        print(f"[{e.type.upper()}] {e.value} (Pág {e.page}) - Conf: {e.confidence} | '{e.source_text}'")

if __name__ == "__main__":
    run_phase4()
