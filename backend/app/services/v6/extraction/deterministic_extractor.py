from typing import List
from .provider import RequirementExtractionProvider, RequirementCandidate
import re

class DeterministicRequirementExtractor(RequirementExtractionProvider):
    def extract(self, text: str, source_document: str, source_page: int = 1) -> List[RequirementCandidate]:
        # Implementación Sprint 2: Generar propuestas sin decisiones. 
        # Busca viñetas u obligaciones.
        candidates = []
        
        # Simple heuristic split for demonstration (Sprint 2 non-regex/non-LLM full parser)
        lines = text.split("\n")
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # If line seems like a requirement (starts with bullet, or length > 10)
            if len(line) > 15:
                candidates.append(
                    RequirementCandidate(
                        requirement_type="TECHNICAL",
                        description=line,
                        value=None,
                        mandatory=True,
                        source_document=source_document,
                        source_page=source_page,
                        source_fragment=line,
                        confidence=0.6 # Moderate confidence, forcing human review
                    )
                )
        
        return candidates
