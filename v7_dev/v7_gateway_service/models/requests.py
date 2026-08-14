from pydantic import BaseModel, Field

class SanitizeRequest(BaseModel):
    request_id: str
    tenant_context: str
    policy_version: str
    schema_version: str = "v7.0"
    content: str

class ValidateRequest(BaseModel):
    request_id: str
    tenant_context: str
    policy_version: str
    schema_version: str = "v7.0"
    ai_response: str
    evidence_ids: list[str] = []

class RouteRequest(BaseModel):
    request_id: str
    tenant_context: str
    policy_version: str
    schema_version: str = "v7.0"
    query: str
