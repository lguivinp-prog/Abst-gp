import hashlib
import json
from datetime import datetime

class GatewayAuditEventInterface:
    def __init__(self):
        self.logs = []
        
    def log_event(self, request_id: str, decision: str, versions: dict):
        timestamp = datetime.now().isoformat()
        
        event = {
            "request_id": request_id,
            "decision": decision,
            "versions": versions,
            "timestamp": timestamp
        }
        
        event_str = json.dumps(event, sort_keys=True)
        audit_hash = hashlib.sha256(event_str.encode()).hexdigest()
        
        event["hash"] = audit_hash
        self.logs.append(event)
        
        # In a real system, send this to Splunk/Elasticsearch securely
        print(f"[AUDIT] {json.dumps(event)}")
        return audit_hash

audit_logger = GatewayAuditEventInterface()
