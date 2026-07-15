import os
import time
import json
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

def run_pipeline(pdf_path: str, run_index: int) -> StructuredDocument:
    print(f"\n--- RUN {run_index} ---")
    doc = StructuredDocument()
    
    print("1. Classification...")
    classifier = PdfClassifier()
    cls_result = classifier.classify(pdf_path)
    doc.metadata["document_type"] = cls_result.document_type
    
    print("2. Preprocessing images...")
    preprocessor = ImagePreprocessor(base_output_dir="/data/processed")
    img_result = preprocessor.process(f"doc_reg_run_{run_index}", pdf_path)
    processed_images = img_result["processed_images"]
    
    print("3. OCR & Layout...")
    import cv2
    ocr_engine = HybridOcrEngine()
    layout_analyzer = LayoutAnalyzer()
    
    doc_blocks = []
    
    for i, img_path in enumerate(processed_images):
        page_num = i + 1
        print(f"   Procesando Página {page_num}...")
        image = cv2.imread(img_path)
        ocr_result = ocr_engine.extract(image, page_number=page_num)
        elements = ocr_result["elements"]
        
        doc.pages.append(DocumentPage(
            page_number=page_num,
            width=float(image.shape[1]),
            height=float(image.shape[0]),
            elements=elements
        ))
        
        layout_result = layout_analyzer.analyze(elements)
        for b in layout_result["blocks"]:
            doc_blocks.append(DocumentBlock(
                type=b["type"],
                content=b["text"],
                page=page_num,
                bounding_box=b["bounding_box"],
                style=b.get("style", {})
            ))
            
    doc.blocks = doc_blocks
    
    print("4. Header/Footer Detection...")
    hf_detector = HeaderFooterDetector()
    doc = hf_detector.process(doc)
    
    print("5. Table Detection...")
    table_detector = TableDetector()
    doc = table_detector.process(doc, pdf_path)
    
    print("6. Semantic Section Parsing...")
    semantic_parser = SemanticSectionParser()
    doc = semantic_parser.process(doc)
    
    print("7. Contract Entity Extraction...")
    entity_extractor = ContractEntityExtractor()
    doc = entity_extractor.process(doc)
    
    return doc

def check_traceability(doc: StructuredDocument):
    print("\n--- TRAZABILIDAD AUDIT ---")
    errors = 0
    
    # Blocks
    for b in doc.blocks:
        if not b.bounding_box:
            print(f"[ERROR] Block sin bounding_box: {b.content[:30]}")
            errors += 1
        if not hasattr(b, "confidence"):
            print(f"[ERROR] Block sin confidence: {b.content[:30]}")
            errors += 1
            
    # Tables
    for t in doc.tables:
        if not t.bounding_box:
            print(f"[ERROR] Tabla sin bounding_box en pag {t.page_number}")
            errors += 1
        if not t.extraction_method:
            print(f"[ERROR] Tabla sin extraction_method en pag {t.page_number}")
            errors += 1
            
    # Entities
    for e in doc.entities:
        if not getattr(e, "bounding_box", None) and getattr(e, "bounding_box", None) != {}:
            pass # We didn't heavily implement bbox for entities yet, but it exists
            
    if errors == 0:
        print("[OK] Trazabilidad 100% confirmada en bloques y tablas.")
    else:
        print(f"[WARNING] Se encontraron {errors} errores de trazabilidad.")

def main():
    pdf_path = "/data/uploads/0fc2be49-e700-4383-940b-08e6e6cc2d31.pdf"
    
    if not os.path.exists(pdf_path):
        print(f"Archivo no encontrado: {pdf_path}")
        return
        
    evaluator = OcrEvaluator()
    results = []
    
    for i in range(1, 4):
        start_time = time.time()
        doc = run_pipeline(pdf_path, i)
        end_time = time.time()
        
        eval_result = evaluator.evaluate(doc)
        
        results.append({
            "run": i,
            "time_seconds": end_time - start_time,
            "sections": len([b for b in doc.blocks if b.type == "section"]),
            "tables": len(doc.tables),
            "entities": len(doc.entities),
            "score": eval_result
        })
        
        if i == 1:
            check_traceability(doc)
            print("\n--- BLOCKS TEXT ---")
            for b in doc.blocks:
                print(f"[{b.type}] {b.content}")
                if b.type == "section" or b.type == "heading":
                    print(f"  -> NORMALIZED: {getattr(b, 'normalized_text', 'None')}")
            
    print("\n================ OCR V2 REGRESSION TEST ================")
    for r in results:
        print(f"\n[RUN {r['run']}] ({r['time_seconds']:.2f}s)")
        print(f"Secciones: {r['sections']}")
        print(f"Tablas: {r['tables']}")
        print(f"Entidades: {r['entities']}")
        print(f"Evaluación: {json.dumps(r['score'], indent=2)}")
        
if __name__ == "__main__":
    main()
