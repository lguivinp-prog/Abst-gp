from fastapi import HTTPException
from app.models.domain import CaseFile

def ensure_requirement_review_valid(case: CaseFile):
    """
    Ensures that the case requirement review is valid before allowing quotation-stage mutations.
    """
    valid_statuses = [
        "WAITING_QUOTATION",
        "COMPARING",
        "READY_GENERATE",
        "UNDER_REVIEW",
        "APPROVED",
        "COMPLETED"
    ]
    if case.status not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail="Requirement review is pending or invalid. Please confirm requirements before proceeding."
        )
