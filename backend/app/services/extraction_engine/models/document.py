from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any, Union

class PageClassification(BaseModel):
    page_number: int
    needs_ocr: bool
    native_text_length: int

class OcrElement(BaseModel):
    text: str
    confidence: float
    x: float
    y: float
    width: float
    height: float
    page_number: int
    source: str = "paddleocr"

class DocumentBlock(BaseModel):
    type: str
    content: Union[str, List[Any], Dict[str, Any]]
    original_text: Optional[str] = None
    normalized_text: Optional[str] = None
    style: Dict[str, Any] = Field(default_factory=dict)
    bounding_box: Dict[str, float] = Field(default_factory=dict)
    page: int
    confidence: float = 0.0
    source_elements: List[OcrElement] = Field(default_factory=list)
    transformations: List[str] = Field(default_factory=list)
    source: str = "ocr_v2"

class DocumentPage(BaseModel):
    page_number: int
    width: float
    height: float
    elements: List[OcrElement] = Field(default_factory=list)

class TableBlock(BaseModel):
    type: str = "table"
    columns: List[str] = Field(default_factory=list)
    rows: List[List[str]] = Field(default_factory=list)
    bounding_box: Dict[str, float] = Field(default_factory=dict)
    page_number: int
    confidence: float
    extraction_method: str
    elements_used: List[OcrElement] = Field(default_factory=list)
    transformations: List[str] = Field(default_factory=list)

class ContractEntity(BaseModel):
    type: str
    value: str
    source_text: str
    page: int
    confidence: float
    bounding_box: Dict[str, float] = Field(default_factory=dict)
    transformations: List[str] = Field(default_factory=list)

class StructuredDocument(BaseModel):
    metadata: Dict[str, Any] = Field(default_factory=dict)
    pages: List[DocumentPage] = Field(default_factory=list)
    blocks: List[DocumentBlock] = Field(default_factory=list)
    tables: List[TableBlock] = Field(default_factory=list)
    entities: List[ContractEntity] = Field(default_factory=list)
    confidence: float = 0.0
    warnings: List[str] = Field(default_factory=list)

class PdfClassificationResult(BaseModel):
    document_type: str # digital, scanned, hybrid
    confidence: float
    pages: int
    text_pages: int
    image_pages: int
    details: Dict[str, Any] = Field(default_factory=dict)
    page_results: List[PageClassification] = Field(default_factory=list)
