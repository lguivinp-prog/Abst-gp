from abc import ABC, abstractmethod
from typing import List, Optional
from pydantic import BaseModel

class RequirementCandidate(BaseModel):
    requirement_type: str
    description: str
    value: Optional[str] = None
    mandatory: bool
    source_document: str
    source_page: int
    source_fragment: str
    confidence: float

class RequirementExtractionProvider(ABC):
    @abstractmethod
    def extract(self, text: str, source_document: str, source_page: int = 1) -> List[RequirementCandidate]:
        """Extracts candidate requirements from text."""
        pass
