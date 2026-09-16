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
    needs_review: bool = False

class ProcurementItemCandidate(BaseModel):
    item_number: str
    description: str
    quantity: Optional[float] = None
    unit: Optional[str] = None
    source_document: str
    source_page: int
    source_fragment: str
    confidence: float
    needs_review: bool = False

class ExtractionResult(BaseModel):
    requirements: List[RequirementCandidate] = []
    items: List[ProcurementItemCandidate] = []

class RequirementExtractionProvider(ABC):
    @abstractmethod
    def extract(self, text: str, source_document: str, source_page: int = 1) -> ExtractionResult:
        """Extracts candidate requirements and items from text."""
        pass
