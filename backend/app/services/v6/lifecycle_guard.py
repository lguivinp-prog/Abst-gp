from fastapi import HTTPException
from app.models.domain import CaseFile

TERMINAL_CASE_STATUSES = {
    "APPROVED",
    "COMPLETED",
}

def ensure_case_mutable(case: CaseFile):
    """
    Ensures that the case is not in a terminal status before allowing mutations.
    """
    if case.status in TERMINAL_CASE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail="Case is in a terminal status and can no longer be modified."
        )
