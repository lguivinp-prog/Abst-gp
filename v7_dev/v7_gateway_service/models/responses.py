from pydantic import BaseModel

class SanitizeResponse(BaseModel):
    request_id: str
    masked_content: str
    decision: str
    audit_hash: str

class ValidateResponse(BaseModel):
    request_id: str
    decision: str
    audit_hash: str

class RouteResponse(BaseModel):
    request_id: str
    target_engine: str
    decision: str
    audit_hash: str
