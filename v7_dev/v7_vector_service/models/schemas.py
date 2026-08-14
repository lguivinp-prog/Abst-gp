from pydantic import BaseModel
from typing import List

class VectorIndexRequest(BaseModel):
    tenant_id: str
    chunk_id: str
    content: str
    embedding: List[float]
    document_hash: str
    embedding_model: str
    embedding_version: str
    source_type: str

class VectorSearchRequest(BaseModel):
    tenant_id: str
    embedding: List[float]
    top_k: int = 5
    timeout_ms: int = 1000

class VectorIndexResponse(BaseModel):
    status: str
    audit_hash: str
    latency_ms: float

class ChunkResult(BaseModel):
    chunk_id: str
    content: str
    distance: float

class VectorSearchResponse(BaseModel):
    results: List[ChunkResult]
    audit_hash: str
    latency_ms: float
