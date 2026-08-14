from app.models.v6.ciiu_catalog import CiiuCatalog
from sqlalchemy.orm import Session
from typing import Dict, List, Optional

class DeterministicCIIUMatcher:
    def __init__(self, db: Session):
        self.db = db
        
    def match_activities(self, ciiu_codes: List[str], target_description: str) -> Dict[str, str]:
        results = {}
        for code in ciiu_codes:
            catalog_entry = self.db.query(CiiuCatalog).filter(CiiuCatalog.code == code).first()
            if not catalog_entry:
                results[code] = "UNKNOWN"
                continue
                
            # Deterministic comparison mock for Sprint 3
            # Later: Semantic Matching Engine
            desc_lower = catalog_entry.description.lower()
            target_lower = target_description.lower()
            
            # Simple word overlap
            words_cat = set(desc_lower.split())
            words_target = set(target_lower.split())
            overlap = len(words_cat.intersection(words_target))
            
            if overlap >= 3:
                results[code] = "HIGH"
            elif overlap >= 1:
                results[code] = "MEDIUM"
            else:
                results[code] = "LOW"
                
        return results
