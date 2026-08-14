from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Union

class BBox(BaseModel):
    x0: float
    y0: float
    x1: float
    y1: float

class StructuredCell(BaseModel):
    text: str
    bbox: Optional[BBox] = None
    row_span: int = 1
    col_span: int = 1
    confidence: Optional[float] = None
    manual_required: bool = False

class StructuredRow(BaseModel):
    cells: List[StructuredCell]
    bbox: Optional[BBox] = None

class StructuredTable(BaseModel):
    rows: List[StructuredRow]
    row_count: int
    col_count: int
    bbox: Optional[BBox] = None
    confidence: Optional[float] = None
    manual_required: bool = False

class StructuredBlock(BaseModel):
    type: str  # HEADING, PARAGRAPH, LIST, LIST_ITEM, TABLE, FORMULA_OR_LAYOUT_BLOCK, NOTE
    text: Optional[str] = None
    bbox: Optional[BBox] = None
    page_num: int
    reading_order: int
    children: Optional[List['StructuredBlock']] = None
    table_data: Optional[StructuredTable] = None
    confidence: Optional[float] = None
    manual_required: bool = False
    source_method: str = "native" # native, ocr_blocks, ocr_tables

# Allow recursive references
StructuredBlock.model_rebuild()

class StructuredPage(BaseModel):
    page_num: int
    blocks: List[StructuredBlock]
    width: float
    height: float
    source_type: str  # digital, scanned, mixed

class StructuredDocument(BaseModel):
    schema_version: int = 1
    pages: List[StructuredPage]
    metadata: Dict[str, Any] = Field(default_factory=dict)
