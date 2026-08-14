import re
import time
import tracemalloc

# --- PIPELINE DATASET ---
SAFE_PAGE = "CONTRATO DE SERVICIOS\nEste es un texto limpio que no contiene ningun tipo de dato personal. " * 50
PII_PAGE = SAFE_PAGE + " RUC 20123456789. "

class PIIMatch:
    def __init__(self, start, end, label, text):
        self.start = start
        self.end = end
        self.label = label
        self.text = text

# --- FASE 2: EXCEPTION MANAGEMENT ---
class GatewayPolicyException:
    def __init__(self, pattern, reason, creator, approver, expiration, version):
        self.pattern = pattern
        self.reason = reason
        self.creator = creator
        self.approver = approver
        self.expiration = expiration
        self.version = version

class PIIDetectionEngine:
    def __init__(self):
        self.rule_set_version = "v1.2"
        self.patterns = [
            ("RUC", re.compile(r'\b(10|20)\d{9}\b')),
            ("DNI", re.compile(r'\b\d{8}\b')),
        ]
        
    def detect(self, text):
        matches = []
        for label, regex in self.patterns:
            for match in regex.finditer(text):
                matches.append(PIIMatch(match.start(), match.end(), label, match.group()))
        return matches

class PositionBasedMaskingEngine:
    def __init__(self):
        self.version = "1.2"
        
    def mask(self, text, resolved_matches):
        resolved_matches.sort(key=lambda x: x.start, reverse=True)
        masked_text = text
        for match in resolved_matches:
            tag = f"[{match.label}_MASKED]"
            masked_text = masked_text[:match.start] + tag + masked_text[match.end:]
        return masked_text

class GatewayPolicyEngine:
    def __init__(self):
        self.version = "3.0"
        self.exception_set_version = "v1.0"
        self.exceptions = [
            GatewayPolicyException(r'\b9\d{8}\b', "Telefono", "Admin", "CISO", "2027-01-01", self.exception_set_version)
        ]
        
    def evaluate(self, masked_text, matches_found):
        clean_text = masked_text
        for exc in self.exceptions:
            clean_text = re.sub(exc.pattern, '', clean_text)
            
        residual = re.search(r'\d{8,}', clean_text)
        if residual:
            return "BLOCK"
        
        if matches_found > 0:
            return "ALLOW" # Limpiado
            
        return "ALLOW"

class GatewayAuditEvent:
    def __init__(self, decision, rule_v, exc_v):
        self.decision = decision
        self.rule_set_version = rule_v
        self.exception_set_version = exc_v

def process_chunk(chunk, detector, masker, policy):
    matches = detector.detect(chunk)
    matches.sort(key=lambda x: (x.start, -(x.end - x.start)))
    resolved = []
    last_end = -1
    for match in matches:
        if match.start >= last_end:
            resolved.append(match)
            last_end = match.end
            
    masked = masker.mask(chunk, resolved)
    dec = policy.evaluate(masked, len(resolved))
    return dec

def run_pipeline_streaming(pages_list):
    detector = PIIDetectionEngine()
    masker = PositionBasedMaskingEngine()
    policy = GatewayPolicyEngine()
    
    final_decision = "ALLOW"
    for chunk in pages_list:
        dec = process_chunk(chunk, detector, masker, policy)
        if dec == "BLOCK":
            final_decision = "BLOCK"
            break
            
    audit = GatewayAuditEvent(final_decision, detector.rule_set_version, policy.exception_set_version)
    return final_decision

# --- FASE 4: ADVANCED BENCHMARK ---
def run_advanced_benchmark():
    print("\n--- ADVANCED STREAMING BENCHMARK (1000 Pages) ---")
    
    # Escenario A: PII en Pagina 1
    doc_a = [PII_PAGE] + [SAFE_PAGE] * 999
    
    # Escenario B: PII en Pagina 999
    doc_b = [SAFE_PAGE] * 998 + [PII_PAGE] + [SAFE_PAGE]
    
    # Escenario C: Sin PII
    doc_c = [SAFE_PAGE] * 1000
    
    scenarios = [("PII en Pág 1", doc_a), ("PII en Pág 999", doc_b), ("Sin PII", doc_c)]
    
    for name, doc in scenarios:
        tracemalloc.start()
        start_t = time.time()
        
        dec = run_pipeline_streaming(doc)
        
        end_t = time.time()
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        
        print(f"Scenario: {name:15s} | Time: {(end_t - start_t)*1000:7.2f} ms | RAM Peak: {peak / 1024 / 1024:6.2f} MB | Decision: {dec}")

if __name__ == "__main__":
    run_advanced_benchmark()
