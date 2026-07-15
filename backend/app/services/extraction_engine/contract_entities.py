import re
from app.services.extraction_engine.models.document import StructuredDocument, ContractEntity

class ContractEntityExtractor:
    def __init__(self):
        self.delivery_pattern = re.compile(r'(\d+)\s+(d[iííl1]as|meses)', re.IGNORECASE)
        self.warranty_pattern = re.compile(r'(?:garant[ií]a|garantiza).*?(\d+)\s+(meses|a[ñn]os)', re.IGNORECASE | re.DOTALL)
        self.known_payments = ["pago único", "pago unico", "pagos parciales", "pago adelantado", "pago a contra entrega", "pago mensual", "pago en una sola armada"]
        
    def process(self, document: StructuredDocument) -> StructuredDocument:
        entities = []
        for block in document.blocks:
            if block.style.get("remove_from_content"):
                continue
                
            if isinstance(block.content, str):
                text = block.content
                lower_text = text.lower()
                
                # Check Delivery Terms
                if "entrega" in lower_text or "plazo" in lower_text:
                    for match in self.delivery_pattern.finditer(text):
                        val = match.group(0).strip()
                        entities.append(ContractEntity(
                            type="delivery_term",
                            value=val,
                            source_text=text,
                            page=block.page,
                            confidence=0.90
                        ))
                        
                # Check Warranty
                if "garant" in lower_text:
                    found = False
                    for match in self.warranty_pattern.finditer(lower_text):
                        val = f"{match.group(1)} {match.group(2)}"
                        entities.append(ContractEntity(
                            type="warranty",
                            value=val,
                            source_text=text,
                            page=block.page,
                            confidence=0.85
                        ))
                        found = True
                    
                    if not found:
                        fallback_match = re.search(r'(\d+)\s+(meses|a[ñn]os)', text, re.IGNORECASE)
                        if fallback_match:
                            val = f"{fallback_match.group(1)} {fallback_match.group(2)}"
                            entities.append(ContractEntity(
                                type="warranty",
                                value=val,
                                source_text=text,
                                page=block.page,
                                confidence=0.70
                            ))
                    
                # Check Payment
                for kp in self.known_payments:
                    if kp in lower_text:
                        entities.append(ContractEntity(
                            type="payment_condition",
                            value=kp,
                            source_text=text,
                            page=block.page,
                            confidence=0.95
                        ))
                            
        document.entities = entities
        return document
