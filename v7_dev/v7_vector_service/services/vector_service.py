from repositories.pgvector_repo import vector_repo
from models.schemas import VectorIndexRequest, VectorSearchRequest, ChunkResult
import time

class VectorService:
    def index_document(self, req: VectorIndexRequest):
        start_t = time.time()
        
        vector_repo.insert_chunk(
            tenant_id=req.tenant_id,
            chunk_id=req.chunk_id,
            content=req.content,
            embedding=req.embedding,
            doc_hash=req.document_hash,
            model=req.embedding_model,
            version=req.embedding_version,
            source=req.source_type
        )
        
        latency = (time.time() - start_t) * 1000
        return latency

    def search_similar(self, req: VectorSearchRequest):
        start_t = time.time()
        
        rows = vector_repo.search_chunks(
            tenant_id=req.tenant_id,
            query_embedding=req.embedding,
            top_k=req.top_k
        )
        
        latency = (time.time() - start_t) * 1000
        
        results = []
        for row in rows:
            results.append(ChunkResult(chunk_id=row[0], content=row[1], distance=float(row[2])))
            
        return results, latency

vector_service = VectorService()
