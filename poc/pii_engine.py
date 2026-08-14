import re
import time
import tracemalloc

# --- FASE 1: DATASET ANONIMIZADO ---
SAMPLE_DOC = """
CONTRATO DE SERVICIOS
Conste por el presente documento, el contrato que celebran de una parte el MINISTERIO, y de la otra parte la empresa COMPU SYSTEMS S.A.C. con RUC 20123456789, debidamente representada por su Gerente General Juan Perez Garcia, identificado con DNI 12345678, con domicilio legal en Av. Javier Prado Este 456, San Isidro.
El monto total asciende a S/ 50,000.00.
El pago se realizará a la cuenta CCI 002-191-000123456789-50 del Banco de Crédito.
"""

# --- FASE 2: PII DETECTION ENGINE ---
class PIIDetectionEngine:
    def __init__(self):
        # Regex heurísticos peruanos
        self.ruc_pattern = re.compile(r'\b(10|20)\d{9}\b')
        self.dni_pattern = re.compile(r'\b\d{8}\b')
        self.cci_pattern = re.compile(r'\b\d{3}-\d{3}-\d{14}\b')
        self.name_pattern = re.compile(r'\b[A-Z][a-z]+ [A-Z][a-z]+ [A-Z][a-z]+\b') # Mock NER
        
    def detect(self, text):
        found = {
            "RUC": self.ruc_pattern.findall(text),
            "DNI": self.dni_pattern.findall(text),
            "CCI": self.cci_pattern.findall(text)
        }
        return found

# --- FASE 3 & 4: CLASSIFICATION & MASKING ---
class MaskingEngine:
    def __init__(self, detector):
        self.detector = detector
        
    def mask_document(self, text):
        found_pii = self.detector.detect(text)
        masked_text = text
        
        status = "PII_NOT_FOUND"
        has_pii = False
        
        # Masking determinista
        for ruc in found_pii["RUC"]:
            masked_text = masked_text.replace(ruc, "[RUC_MASKED]")
            has_pii = True
            
        for dni in found_pii["DNI"]:
            masked_text = masked_text.replace(dni, "[DNI_MASKED]")
            has_pii = True
            
        for cci in found_pii["CCI"]:
            masked_text = masked_text.replace(cci, "[CCI_MASKED]")
            has_pii = True
            
        if has_pii:
            status = "PII_FOUND"
            
        return status, masked_text

# --- FASE 5: POLICY ENGINE TEST ---
class PolicyEngine:
    def evaluate(self, status, original, masked):
        # Fail Closed: Si sigue habiendo números largos (posibles fallos), block.
        if re.search(r'\d{8,}', masked):
            return "BLOCK" # Quedó un DNI/RUC sin enmascarar!
        if status == "PII_FOUND":
            return "ALLOW" # Limpiado
        if status == "PII_UNCERTAIN":
            return "QUARANTINE"
        return "ALLOW"

# --- FASE 6: PERFORMANCE TEST ---
def run_performance():
    detector = PIIDetectionEngine()
    masker = MaskingEngine(detector)
    policy = PolicyEngine()
    
    pages = [10, 100, 1000]
    words_per_page = 300
    base_text = SAMPLE_DOC * (300 // len(SAMPLE_DOC.split()))
    
    print("--- PERFORMANCE METRICS ---")
    for p in pages:
        test_doc = base_text * p
        
        tracemalloc.start()
        start_t = time.time()
        
        # Flujo Gateway
        status, masked = masker.mask_document(test_doc)
        decision = policy.evaluate(status, test_doc, masked)
        
        end_t = time.time()
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        
        print(f"Pages: {p:4d} | Time: {(end_t - start_t)*1000:6.2f} ms | RAM Peak: {peak / 1024 / 1024:6.2f} MB | Decision: {decision}")
        
if __name__ == "__main__":
    print("--- MASKING TEST ---")
    detector = PIIDetectionEngine()
    masker = MaskingEngine(detector)
    policy = PolicyEngine()
    
    status, masked = masker.mask_document(SAMPLE_DOC)
    decision = policy.evaluate(status, SAMPLE_DOC, masked)
    print(f"Original:\n{SAMPLE_DOC}")
    print(f"Masked:\n{masked}")
    print(f"Status: {status} | Decision: {decision}\n")
    
    run_performance()
