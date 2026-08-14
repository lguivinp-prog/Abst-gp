from fastapi import APIRouter, Depends, HTTPException
from models.schemas import VectorIndexRequest, VectorSearchRequest, VectorIndexResponse, VectorSearchResponse
from services.vector_service import vector_service
from security.tenant_isolation import verify_tenant_context
from audit.event_logger import audit_logger
from main import INDEX_TOTAL, ERRORS_TOTAL, RLS_DENIED_TOTAL

router = APIRouter(prefix="/v7/vector")

@router.post("/index", response_model=VectorIndexResponse)
def index_vector(req: VectorIndexRequest, tenant_id: str = Depends(verify_tenant_context)):
    # Ensure tenant matches the header context to prevent spoofing
    if req.tenant_id != tenant_id:
        RLS_DENIED_TOTAL.inc()
        raise HTTPException(status_code=403, detail="Tenant mismatch between header and payload")

    try:
        latency = vector_service.index_document(req)
        INDEX_TOTAL.inc()
        
        audit_hash = audit_logger.log_operation(
            "INDEX", tenant_id, latency, 1, req.embedding_version
        )
        
        return VectorIndexResponse(status="SUCCESS", audit_hash=audit_hash, latency_ms=latency)
    except Exception as e:
        ERRORS_TOTAL.inc()
        raise e

@router.post("/search", response_model=VectorSearchResponse)
def search_vectors(req: VectorSearchRequest, tenant_id: str = Depends(verify_tenant_context)):
    if req.tenant_id != tenant_id:
        RLS_DENIED_TOTAL.inc()
        raise HTTPException(status_code=403, detail="Tenant mismatch between header and payload")

    try:
        results, latency = vector_service.search_similar(req)
        
        audit_hash = audit_logger.log_operation(
            "SEARCH", tenant_id, latency, len(results), "v7.0"
        )
        
        return VectorSearchResponse(results=results, audit_hash=audit_hash, latency_ms=latency)
    except Exception as e:
        ERRORS_TOTAL.inc()
        raise e
