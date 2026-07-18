from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from uuid import UUID

# Importamos los Enums desde domain para mantener consistencia
from app.models.domain import (
    ComparisonRunStatus,
    RequirementItemType,
    ComparisonResultStatus,
    EvaluationMethod
)

# ---------------------------------------------
# RequirementItem Schemas
# ---------------------------------------------
class RequirementItemBase(BaseModel):
    parsed_section_id: int
    item_type: RequirementItemType
    content_text: str

class RequirementItemCreate(RequirementItemBase):
    pass

class RequirementItemResponse(RequirementItemBase):
    id: UUID
    is_approved: bool

    model_config = {"from_attributes": True}


# ---------------------------------------------
# ComparisonResult Schemas
# ---------------------------------------------
class ComparisonResultBase(BaseModel):
    requirement_item_id: UUID
    quotation_section_id: Optional[int] = None
    status: ComparisonResultStatus
    evaluation_method: EvaluationMethod
    confidence_score: float
    reasoning: Optional[str] = None
    evidence_text: Optional[str] = None
    requirement_page: Optional[int] = None
    quotation_page: Optional[int] = None

class ComparisonResultCreate(ComparisonResultBase):
    pass

class ComparisonResultResponse(ComparisonResultBase):
    id: UUID
    run_id: UUID

    model_config = {"from_attributes": True}


# ---------------------------------------------
# ComparisonRun Schemas
# ---------------------------------------------
class ComparisonRunBase(BaseModel):
    case_id: int
    requirement_doc_id: int
    quotation_doc_id: int

class ComparisonRunCreate(ComparisonRunBase):
    pass

class ComparisonRunResponse(ComparisonRunBase):
    id: UUID
    status: ComparisonRunStatus
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
