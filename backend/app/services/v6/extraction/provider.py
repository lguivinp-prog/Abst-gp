from abc import ABC, abstractmethod
from typing import List, Optional
from pydantic import BaseModel, Field

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

class ItemSpecificationCandidate(BaseModel):
    name: str
    normalized_name: str
    value: str
    mandatory: Optional[str] = None
    source_page: Optional[int] = None
    confidence: float

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
    specifications: List[ItemSpecificationCandidate] = Field(default_factory=list)

class ExtractionResult(BaseModel):
    requirements: List[RequirementCandidate] = Field(default_factory=list)
    items: List[ProcurementItemCandidate] = Field(default_factory=list)

class RequirementExtractionProvider(ABC):
    @abstractmethod
    def extract(self, text: str, source_document: str, source_page: int = 1) -> ExtractionResult:
        """Extracts candidate requirements and items from text."""
        pass
