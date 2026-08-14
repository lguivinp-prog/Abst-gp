import sys
import json
import logging
from app.services.ocr.engine import process_pdf
from app.services.extraction.document_extraction_agent import DocumentExtractionAgent

logging.basicConfig(level=logging.INFO)

def run_regression():
    pdf_path = "/app/data/EETT MATERIALES DE OFICINA - DIRECCIÓN.pdf" # Need to copy it here
    
    print(f"Processing {pdf_path}...")
    try:
        ocr_result = process_pdf(pdf_path)
    except Exception as e:
        print(f"Error in process_pdf: {e}")
        return
        
    try:
        print("Process PDF successful!")
        if ocr_result.errors:
            print("OCR Errors:")
            for err in ocr_result.errors:
                print(err)
        print(f"Schema version: {ocr_result.structured_document.schema_version if ocr_result.structured_document else 'None'}")
        
        agent = DocumentExtractionAgent()
        print("Running extraction agent...")
        print("First 20 blocks in the document:")
        for page in ocr_result.structured_document.pages:
            print(f"Page {page.page_num}: {len(page.blocks)} blocks")
            for block in page.blocks:
                print(f"  [{block.type}]: {repr(block.text)}")
            print("---")
            
        sections = agent.process(ocr_result.pages_text, "bienes", ocr_result.structured_document)
        
        with open("/app/scripts/output.txt", "w", encoding="utf-8") as f:
            f.write(f"Found {len(sections)} sections.\n")
            for i, sec in enumerate(sections):
                title = sec.metadata.get('title', '').upper()
                f.write(f"\n--- Section {i+1}: {title} ({sec.metadata.get('original_roman')}) ---\n")
                
                # Check anchors
                if "CARACTERÍSTICAS" in title:
                    f.write("=== ANCHOR B & C ===\n")
                    f.write(json.dumps(sec.structure_json, indent=2, ensure_ascii=False) + "\n")
                elif "JUSTIFICACIÓN" in title or "OBJETIVO" in title:
                    f.write("=== ANCHOR A ===\n")
                    f.write(json.dumps(sec.structure_json, indent=2, ensure_ascii=False) + "\n")
                elif "10.5" in title or "OBLIGACIONES" in title or "OTRAS CONSIDERACIONES" in title or "CONSIDERACIONES PARA LA EJECUCIÓN" in title:
                    f.write("=== ANCHOR D ===\n")
                    f.write(json.dumps(sec.structure_json, indent=2, ensure_ascii=False) + "\n")
                elif "PENALIDADES" in title and "OTRAS" not in title:
                    f.write("=== ANCHOR E ===\n")
                    f.write(json.dumps(sec.structure_json, indent=2, ensure_ascii=False) + "\n")
                elif "OTRAS PENALIDADES" in title or ("PENALIDADES" in title and "OTRAS" in title):
                    f.write("=== ANCHOR F ===\n")
                    f.write(json.dumps(sec.structure_json, indent=2, ensure_ascii=False) + "\n")
                
            f.write("\nRegression test completed.\n")
    except Exception as e:
        import traceback
        with open("/app/scripts/output.txt", "a", encoding="utf-8") as f:
            f.write("\nEXCEPTION:\n")
            f.write(traceback.format_exc())

if __name__ == "__main__":
    run_regression()
