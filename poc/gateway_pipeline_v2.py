import re
import time
import tracemalloc

# --- FASE 5: FALSE POSITIVE CONTROL DATASET ---
SAMPLE_DOC = """
CONTRATO DE SERVICIOS
Conste por el presente documento, el contrato que celebran de una parte el MINISTERIO, y de la otra parte la empresa COMPU SYSTEMS S.A.C. con RUC 20123456789, debidamente representada por su Gerente General Juan Perez Garcia, identificado con DNI 12345678, con domicilio legal en Av. Javier Prado Este 456, San Isidro.
El monto total asciende a S/ 50,000.00.
El pago se realizará a la cuenta CCI 002-191-000123456789-50 del Banco de Crédito.
Falsos Positivos Tests:
- Teléfono: 987654321
- Expediente: EXP-2026-98765432
"""

class PIIMatch:
    def __init__(self, start, end, label, text, confidence="HIGH"):
        self.start = start
        self.end = end
        self.label = label
        self.text = text
        self.confidence = confidence

class PIIDetectionEngine:
    def __init__(self):
        self.version = "1.1"
        self.patterns = [
            ("RUC", re.compile(r'\b(10|20)\d{9}\b')),
            ("DNI", re.compile(r'\b\d{8}\b')),
            ("CCI", re.compile(r'\b\d{3}-\d{3}-\d{14}\b')),
            # Exclusions to prevent false positives
            ("PHONE", re.compile(r'\b9\d{8}\b')), # Phone starts with 9 in Peru
            ("EXPEDIENTE", re.compile(r'EXP-\d{4}-\d{8}'))
        ]
        
    def detect(self, text):
        matches = []
        for label, regex in self.patterns:
            for match in regex.finditer(text):
                matches.append(PIIMatch(match.start(), match.end(), label, match.group()))
        return matches

class PIIConflictResolver:
    def resolve(self, matches):
        matches.sort(key=lambda x: (x.start, -(x.end - x.start)))
        resolved = []
        last_end = -1
        for match in matches:
            if match.start >= last_end:
                resolved.append(match)
                last_end = match.end
        # Filter out safe types from being masked
        return [m for m in resolved if m.label not in ("PHONE", "EXPEDIENTE")]

class PositionBasedMaskingEngine:
    def __init__(self):
        self.version = "1.1"
        
    def mask(self, text, resolved_matches):
        resolved_matches.sort(key=lambda x: x.start, reverse=True)
        masked_text = text
        for match in resolved_matches:
            tag = f"[{match.label}_MASKED]"
            masked_text = masked_text[:match.start] + tag + masked_text[match.end:]
        return masked_text

class GatewayPolicyEngine:
    def __init__(self):
        self.version = "2.0"
        
    def evaluate(self, masked_text, matches_found):
        # Scan for residual digits ignoring known safe patterns
        clean_text = re.sub(r'\b9\d{8}\b', '', masked_text) # Ignore phones
        clean_text = re.sub(r'EXP-\d{4}-\d{8}', '', clean_text) # Ignore expedientes
        
        residual = re.search(r'\d{8,}', clean_text)
        if residual:
            return "HIGH_RISK_BLOCK"
        
        if matches_found > 0:
            return "LOW_RISK_ALLOW"
            
        return "LOW_RISK_ALLOW"

class GatewayAuditEvent:
    def __init__(self, decision, matches_count, v_det, v_mask, v_pol):
        self.decision = decision
        self.matches = matches_count
        self.detector_version = v_det
        self.masking_version = v_mask
        self.policy_version = v_pol

# --- FASE 1: STREAMING PIPELINE ---
def process_chunk(chunk, detector, resolver, masker, policy):
    t_start = time.time()
    
    # Det
    t0 = time.time()
    raw = detector.detect(chunk)
    t_det = time.time() - t0
    
    # Res
    res = resolver.resolve(raw)
    
    # Mask
    t0 = time.time()
    masked = masker.mask(chunk, res)
    t_mask = time.time() - t0
    
    # Pol
    t0 = time.time()
    dec = policy.evaluate(masked, len(res))
    t_pol = time.time() - t0
    
    return masked, dec, len(res), t_det, t_mask, t_pol

def run_pipeline_streaming(text, chunk_size=2000):
    detector = PIIDetectionEngine()
    resolver = PIIConflictResolver()
    masker = PositionBasedMaskingEngine()
    policy = GatewayPolicyEngine()
    
    masked_chunks = []
    total_matches = 0
    final_decision = "LOW_RISK_ALLOW"
    
    # Profiling metrics
    tot_det = 0
    tot_mask = 0
    tot_pol = 0
    
    # Chunking
    for i in range(0, len(text), chunk_size):
        chunk = text[i:i+chunk_size]
        masked, dec, m_count, t_det, t_mask, t_pol = process_chunk(chunk, detector, resolver, masker, policy)
        
        masked_chunks.append(masked)
        total_matches += m_count
        tot_det += t_det
        tot_mask += t_mask
        tot_pol += t_pol
        
        if dec == "HIGH_RISK_BLOCK":
            final_decision = "HIGH_RISK_BLOCK"
            # Fail closed immediately
            break
            
    audit = GatewayAuditEvent(final_decision, total_matches, detector.version, masker.version, policy.version)
    return final_decision, "".join(masked_chunks), audit, tot_det, tot_mask, tot_pol

def run_performance():
    pages = [100, 500, 1000]
    base_text = SAMPLE_DOC * (300 // len(SAMPLE_DOC.split()))
    
    print("\n--- STREAMING PERFORMANCE METRICS ---")
    for p in pages:
        test_doc = base_text * p
        
        tracemalloc.start()
        start_t = time.time()
        
        dec, masked, audit, t_det, t_mask, t_pol = run_pipeline_streaming(test_doc)
        
        end_t = time.time()
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        
        print(f"Pages: {p:4d} | Time: {(end_t - start_t)*1000:7.2f} ms | RAM Peak: {peak / 1024 / 1024:6.2f} MB | Decision: {dec}")
        if p == 1000:
             print(f"   -> Profiling (1000p): Det={t_det*1000:.2f}ms, Mask={t_mask*1000:.2f}ms, Pol={t_pol*1000:.2f}ms")

if __name__ == "__main__":
    print("--- FALSE POSITIVE & STREAMING TEST ---")
    dec, masked, audit, _, _, _ = run_pipeline_streaming(SAMPLE_DOC)
    print(f"Original:\n{SAMPLE_DOC}")
    print(f"Masked:\n{masked}")
    print(f"Decision: {dec} | Matches: {audit.matches}")
    
    run_performance()
