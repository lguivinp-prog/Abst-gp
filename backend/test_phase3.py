import os
import cv2
import json
import tracemalloc
from app.services.extraction_engine.image_preprocessor import ImagePreprocessor
from app.services.extraction_engine.ocr_engine import HybridOcrEngine
from app.services.extraction_engine.layout_analyzer import LayoutAnalyzer

def run_phase3():
    tracemalloc.start()
    
    pdf_path = "/data/uploads/0fc2be49-e700-4383-940b-08e6e6cc2d31.pdf"
    if not os.path.exists(pdf_path):
        print("PDF not found!")
        return

    print("--- 1. Image Preprocessing ---")
    preprocessor = ImagePreprocessor(base_output_dir="/data/processed")
    img_result = preprocessor.process("doc_phase3", pdf_path)
    processed_images = img_result["processed_images"]
    
    # We only care about page 1 and page 3 for the benchmark
    # 0-indexed: Page 1 is index 0, Page 3 is index 2
    pages_to_test = [0, 2]
    
    print("\n--- 2. OCR Engine Initialization ---")
    ocr = HybridOcrEngine()
    layout = LayoutAnalyzer()
    
    total_elements = 0
    total_time = 0
    avg_confidences = []
    
    report = {
        "Documento": "77231_EETT INSUMOS PPCHL.pdf",
        "Páginas procesadas": len(pages_to_test),
        "Resultados": []
    }
    
    for page_idx in pages_to_test:
        if page_idx >= len(processed_images):
            continue
            
        print(f"\nProcesando Página {page_idx + 1}...")
        img_path = processed_images[page_idx]
        image = cv2.imread(img_path)
        
        # 3. Extract OCR
        ocr_result = ocr.extract(image, page_number=page_idx + 1)
        elements = ocr_result["elements"]
        stats = ocr_result["stats"]
        
        total_elements += len(elements)
        total_time += stats["time_seconds"]
        
        page_conf = sum(e.confidence for e in elements) / len(elements) if elements else 0
        avg_confidences.append(page_conf)
        
        print(f"Engine: {stats['engine']} | Elementos: {len(elements)} | Confianza media: {page_conf:.2f} | Tiempo: {stats['time_seconds']:.2f}s")
        
        # 4. Layout Analysis
        layout_result = layout.analyze(elements)
        blocks = layout_result["blocks"]
        
        report["Resultados"].append({
            "pagina": page_idx + 1,
            "elementos_ocr": len(elements),
            "confianza_media": page_conf,
            "tiempo": stats["time_seconds"],
            "bloques_layout": blocks
        })
        
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    
    print("\n================ OCR ENGINE REPORT ================")
    print(f"Documento: 77231_EETT INSUMOS PPCHL.pdf")
    print(f"Páginas procesadas: {len(pages_to_test)}")
    print(f"Elementos OCR: {total_elements}")
    print(f"Confianza promedio: {(sum(avg_confidences)/len(avg_confidences))*100:.1f}%" if avg_confidences else "0%")
    print(f"Tiempo promedio página: {(total_time/len(pages_to_test)):.2f} segundos")
    print(f"Memoria Pico: {peak / 10**6:.2f} MB")
    print("Errores: Ninguno reportado.")
    print("====================================================\n")
    
    # Save partial structured output to see the layout result
    with open("/data/processed/doc_phase3/layout_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
        
    print("El detalle del Layout fue guardado en /data/processed/doc_phase3/layout_report.json")
    print("\nMuestra de bloques Página 1:")
    for b in report["Resultados"][0]["bloques_layout"][:5]:
        print(f"[{b['type'].upper()}] {b['text'][:60]}...")
        
    if len(report["Resultados"]) > 1:
        print("\nMuestra de bloques Página 3:")
        for b in report["Resultados"][1]["bloques_layout"][:5]:
            print(f"[{b['type'].upper()}] {b['text'][:60]}...")

if __name__ == "__main__":
    run_phase3()
