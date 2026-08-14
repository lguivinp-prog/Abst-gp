import re
import time
import tracemalloc

# --- FASE 1: PIPELINE DATASET ---
SAMPLE_DOC = """
CONTRATO DE SERVICIOS
Conste por el presente documento, el contrato que celebran de una parte el MINISTERIO, y de la otra parte la empresa COMPU SYSTEMS S.A.C. con RUC 20123456789, debidamente representada por su Gerente General Juan Perez Garcia, identificado con DNI 12345678, con domicilio legal en Av. Javier Prado Este 456, San Isidro.
El monto total asciende a S/ 50,000.00.
El pago se realizará a la cuenta CCI 002-191-000123456789-50 del Banco de Crédito.
"""

# --- FASE 4: CONFIDENCE MODEL & CLASSES ---
class PIIMatch:
    def __init__(self, start, end, label, text, confidence="HIGH"):
        self.start = start
        self.end = end
        self.label = label
        self.text = text
        self.confidence = confidence

# --- FASE 2: DETECTION & CONFLICT RESOLUTION ---
class PIIDetectionEngine:
    def __init__(self):
        # Patterns with labeled types
        self.patterns = [
            ("RUC", re.compile(r'\b(10|20)\d{9}\b')),
            ("DNI", re.compile(r'\b\d{8}\b')),
            ("CCI", re.compile(r'\b\d{3}-\d{3}-\d{14}\b'))
        ]
        
    def detect(self, text):
        matches = []
        for label, regex in self.patterns:
            for match in regex.finditer(text):
                # Basic confidence rules: structural regexes like CCI and RUC are HIGH.
                conf = "HIGH"
                matches.append(PIIMatch(match.start(), match.end(), label, match.group(), conf))
        return matches

class PIIConflictResolver:
    def resolve(self, matches):
        # Sort matches by start position, then by length (longest first)
        matches.sort(key=lambda x: (x.start, -(x.end - x.start)))
        
        resolved = []
        last_end = -1
        
        for match in matches:
            # Overlap check
            if match.start >= last_end:
                resolved.append(match)
                last_end = match.end
            else:
                # Conflict: Match with greater length (RUC over DNI inside RUC) inherently won because of sort order.
                pass 
                
        return resolved

# --- FASE 3: POSITION BASED MASKING ---
class PositionBasedMaskingEngine:
    def mask(self, text, resolved_matches):
        # Masking from end to start to avoid shifting indices
        resolved_matches.sort(key=lambda x: x.start, reverse=True)
        
        masked_text = text
        for match in resolved_matches:
            tag = f"[{match.label}_MASKED]"
            masked_text = masked_text[:match.start] + tag + masked_text[match.end:]
            
        return masked_text

# --- FASE 5: POLICY ENGINE ---
class GatewayPolicyEngine:
    def evaluate(self, masked_text, has_matches):
        # Fail Closed checks
        # Si todavía quedan números grandes (ej. 8+ dígitos) tras el enmascaramiento, bloquear.
        residual_digits = re.search(r'\d{8,}', masked_text)
        if residual_digits:
            return "BLOCK"
            
        # Si habían matches y pasaron la limpieza, ALLOW.
        if has_matches:
            return "ALLOW"
            
        return "QUARANTINE"

# --- FASE 7: SECURITY AUDIT ---
class GatewayAuditEvent:
    def __init__(self, decision, matches_count):
        self.timestamp = time.time()
        self.decision = decision
        self.policy_version = "v1.0"
        self.matches_detected = matches_count

# --- PIPELINE INTEGRATION & PERFORMANCE ---
def run_pipeline(text):
    detector = PIIDetectionEngine()
    resolver = PIIConflictResolver()
    masker = PositionBasedMaskingEngine()
    policy = GatewayPolicyEngine()
    
    # 1. Detection
    raw_matches = detector.detect(text)
    
    # 2. Conflict Resolution
    resolved = resolver.resolve(raw_matches)
    
    # 3. Masking
    masked_text = masker.mask(text, resolved)
    
    # 4. Policy Decision
    decision = policy.evaluate(masked_text, len(resolved) > 0)
    
    # 5. Audit
    audit = GatewayAuditEvent(decision, len(resolved))
    
    return decision, masked_text, audit

def run_performance():
    pages = [100, 500, 1000]
    base_text = SAMPLE_DOC * (300 // len(SAMPLE_DOC.split()))
    
    print("\n--- PERFORMANCE METRICS ---")
    for p in pages:
        test_doc = base_text * p
        
        tracemalloc.start()
        start_t = time.time()
        
        decision, masked, audit = run_pipeline(test_doc)
        
        end_t = time.time()
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        
        print(f"Pages: {p:4d} | Time: {(end_t - start_t)*1000:7.2f} ms | RAM Peak: {peak / 1024 / 1024:6.2f} MB | Decision: {decision}")

if __name__ == "__main__":
    print("--- GATEWAY PIPELINE TEST ---")
    decision, masked, audit = run_pipeline(SAMPLE_DOC)
    print(f"Original:\n{SAMPLE_DOC}")
    print(f"Masked:\n{masked}")
    print(f"Decision: {decision} | Matches found: {audit.matches_detected}")
    
    run_performance()
