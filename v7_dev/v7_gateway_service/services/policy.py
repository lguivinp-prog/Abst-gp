import re

class PolicyService:
    def evaluate_request(self, masked_text: str):
        # Fail Closed if numbers > 8 digits remain
        if re.search(r'\d{8,}', masked_text):
            return "BLOCK"
        return "ALLOW"
        
    def evaluate_response(self, ai_response: str, evidence_ids: list):
        if not evidence_ids:
            return "BLOCK_NO_EVIDENCE"
        return "ALLOW"

policy_service = PolicyService()
