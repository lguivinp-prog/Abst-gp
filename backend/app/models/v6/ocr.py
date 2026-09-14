from pydantic import BaseModel
from typing import List, Optional, Any, Dict

class BBox(BaseModel):
    x0: float
    y0: float
    x1: float
    y1: float

class StructuredCell(BaseModel):
    text: str
    bbox: Optional[BBox] = None
    col_span: int = 1
    row_span: int = 1

class StructuredRow(BaseModel):
    cells: List[StructuredCell]

class StructuredTable(BaseModel):
    rows: List[StructuredRow]
    row_count: int
    col_count: int
    bbox: BBox

class StructuredBlock(BaseModel):
    type: str  # "PARAGRAPH", "TABLE", "LIST_ITEM", "HEADING"
    text: Optional[str] = None
    page_num: int
    reading_order: int
    bbox: Optional[BBox] = None
    table_data: Optional[StructuredTable] = None
    source_method: str = "native"

class StructuredPage(BaseModel):
    page_num: int
    blocks: List[StructuredBlock]
    width: float
    height: float
    source_type: str  # "digital" or "scanned"

class StructuredDocument(BaseModel):
    schema_version: int = 1
    pages: List[StructuredPage]
    metadata: Dict[str, Any]
