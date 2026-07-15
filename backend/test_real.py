import os
from app.services.extraction_engine.pdf_classifier import PdfClassifier
from app.services.extraction_engine.image_preprocessor import ImagePreprocessor
import json
import tracemalloc

def run_test():
    # Start memory tracing
    tracemalloc.start()
    
    # Path inside the container (uploaded file)
    # The container mounts uploads to /data/uploads
    # Let's see if the file is there. If not, we'll search for it or assume a known path.
    # The host path is C:\Users\PC\Documents\AbastLG\Abst-gp\uploads
    
    pdf_path = "/data/uploads/0fc2be49-e700-4383-940b-08e6e6cc2d31.pdf"
    
    if not os.path.exists(pdf_path):
        # Maybe it's directly in the uploads folder
        pdf_dir = "/data/uploads"
        files = os.listdir(pdf_dir) if os.path.exists(pdf_dir) else []
        matching = [f for f in files if "77231" in f]
        if matching:
            pdf_path = os.path.join(pdf_dir, matching[0])
        else:
            print("ERROR: Test PDF not found in /data/uploads. Files found:", files)
            return

    print(f"Testing with file: {pdf_path}")
    
    # 1. Classification
    classifier = PdfClassifier(text_length_threshold=150)
    result = classifier.classify(pdf_path)
    print("--- Classification Result ---")
    print(json.dumps(result.model_dump(), indent=2))
    
    # 2. Image Preprocessing
    print("\n--- Image Preprocessing ---")
    preprocessor = ImagePreprocessor(base_output_dir="/data/processed")
    img_result = preprocessor.process("test_document_123", pdf_path)
    
    print(f"Original images saved: {len(img_result['original_images'])}")
    print(f"Processed images saved: {len(img_result['processed_images'])}")
    print(f"Example original path: {img_result['original_images'][0]}")
    print(f"Example processed path: {img_result['processed_images'][0]}")
    
    # Check memory
    current, peak = tracemalloc.get_traced_memory()
    print(f"\nMemory usage: Current = {current / 10**6}MB, Peak = {peak / 10**6}MB")
    tracemalloc.stop()

if __name__ == "__main__":
    run_test()
