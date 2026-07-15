import os
import time
import requests
import uuid
import yaml
import logging
from concurrent.futures import ThreadPoolExecutor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_URL = os.environ.get("API_URL", "http://localhost:8000/api")
VALIDATION_API_KEY = os.environ.get("VALIDATION_API_KEY", "supersecret_validation_token")
PDF_DIR = os.environ.get("PDF_DIR", "/app/tests/fixtures/pdfs")

def load_policy():
    policy_path = os.environ.get("VALIDATION_POLICY_PATH", "/app/validation_policy.yaml")
    if os.path.exists(policy_path):
        with open(policy_path, "r") as f:
            return yaml.safe_load(f)
    return {
        "warmup": {"documents": 1, "exclude_from_kpis": True},
        "steady_state": {"batch_size": 2, "max_concurrency": 1}
    }

def inject_document(pdf_path: str, validation_run_id: str):
    logger.info(f"Injecting {pdf_path}")
    headers = {"x-api-key": VALIDATION_API_KEY}
    with open(pdf_path, "rb") as f:
        files = {"file": (os.path.basename(pdf_path), f, "application/pdf")}
        data = {"validation_run_id": validation_run_id}
        
        start_time = time.time()
        response = requests.post(f"{API_URL}/validation/upload", headers=headers, files=files, data=data)
        latency = time.time() - start_time
        
        if response.status_code == 200:
            logger.info(f"Success: {response.json()} (Latency: {latency:.2f}s)")
            return response.json()
        else:
            logger.error(f"Failed to inject {pdf_path}: {response.status_code} {response.text}")
            return None

def main():
    policy = load_policy()
    pdfs = [os.path.join(PDF_DIR, f) for f in os.listdir(PDF_DIR) if f.endswith('.pdf')]
    if not pdfs:
        logger.error(f"No PDFs found in {PDF_DIR}")
        return
        
    validation_run_id = str(uuid.uuid4())
    logger.info(f"Starting Validation Run: {validation_run_id}")
    
    # 1. Warm-up
    warmup_count = policy.get("warmup", {}).get("documents", 1)
    if warmup_count > 0 and len(pdfs) > 0:
        warmup_pdf = pdfs.pop(0)
        logger.info("--- WARM-UP ---")
        inject_document(warmup_pdf, validation_run_id)
        # Give it a moment to process before steady state
        time.sleep(5)
        
    # 2. Steady State
    max_concurrency = policy.get("steady_state", {}).get("max_concurrency", 1)
    logger.info(f"--- STEADY STATE (Concurrency: {max_concurrency}) ---")
    
    with ThreadPoolExecutor(max_workers=max_concurrency) as executor:
        for pdf_path in pdfs:
            executor.submit(inject_document, pdf_path, validation_run_id)
            
    logger.info("Injection complete.")

if __name__ == "__main__":
    main()
