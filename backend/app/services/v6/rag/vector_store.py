from abc import ABC, abstractmethod
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from app.models.v6.document_chunk import DocumentChunk

class VectorStoreInterface(ABC):
    @abstractmethod
    def search(self, db: Session, query_embedding: List[float], tenant_id: str, case_id: int, top_k: int = 3) -> List[Dict[str, Any]]:
        pass

class DeterministicVectorStore(VectorStoreInterface):
    def search(self, db: Session, query_embedding: List[float], tenant_id: str, case_id: int, top_k: int = 3) -> List[Dict[str, Any]]:
        """
        Retrieves document chunks for a specific case and tenant.
        Instead of real cosine similarity, this mock deterministic store just returns
        the top chunks sequentially (or pseudo-randomly based on embedding sum) to simulate retrieval,
        but strictly enforces tenant/case boundaries.
        """
        # Strict Boundary Enforcement
        chunks = db.query(DocumentChunk).filter_by(tenant_id=tenant_id, case_id=case_id).limit(top_k).all()
        
        results = []
        for c in chunks:
            # Mocking a similarity score
            score = 0.85 
            results.append({
                "chunk_id": c.id,
                "text": c.text,
                "document_id": c.document_id,
                "page": c.page,
                "score": score
            })
            
        return results
