import hashlib
import json
from datetime import datetime

class VectorAuditEventInterface:
    def __init__(self):
        self.logs = []
        
    def log_operation(self, operation: str, tenant: str, latency: float, result_count: int, vector_version: str):
        event = {
            "operation": operation,
            "tenant": tenant,
            "latency_ms": latency,
            "result_count": result_count,
            "vector_version": vector_version,
            "timestamp": datetime.now().isoformat()
        }
        
        event_str = json.dumps(event, sort_keys=True)
        audit_hash = hashlib.sha256(event_str.encode()).hexdigest()
        
        event["hash"] = audit_hash
        self.logs.append(event)
        
        print(f"[VECTOR AUDIT] {json.dumps(event)}")
        return audit_hash

audit_logger = VectorAuditEventInterface()
