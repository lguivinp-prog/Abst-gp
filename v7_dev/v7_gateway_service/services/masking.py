from .pii_detection import pii_detector

class MaskingService:
    def mask_text(self, text: str):
        matches = pii_detector.detect(text)
        # Conflict Resolver inside Masking: sort by start reverse
        matches.sort(key=lambda x: x["start"], reverse=True)
        
        masked_text = text
        for match in matches:
            tag = f"[{match['label']}_MASKED]"
            masked_text = masked_text[:match["start"]] + tag + masked_text[match["end"]:]
            
        return masked_text

masking_service = MaskingService()
