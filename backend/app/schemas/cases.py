from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime

class CaseBase(BaseModel):
    title: str
    contract_type: str
    
class CaseCreate(CaseBase):
    pass
    
class CaseResponse(CaseBase):
    id: int
    status: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    last_processing_error: Optional[str] = None
    
    model_config = {"from_attributes": True}

class SectionUpdate(BaseModel):
    is_selected: bool
    review_status: str
    current_text: str

class SectionResponse(BaseModel):
    id: int
    case_id: int
    original_roman: Optional[str] = None
    original_order: Optional[int] = None
    title: Optional[str] = None
    original_text: Optional[str] = None
    current_text: Optional[str] = None
    cleaned_text: Optional[str] = None
    normalized_text: Optional[str] = None
    structure_json: Optional[List[Dict[str, Any]]] = None
    corrections_json: Optional[List[Dict[str, Any]]] = None
    warnings_json: Optional[List[Dict[str, Any]]] = None
    extraction_metadata: Optional[Dict[str, Any]] = None
    confidence_score: Optional[float] = None
    is_selected: bool
    review_status: str
    warnings: Optional[str] = None
    
    model_config = {"from_attributes": True}
