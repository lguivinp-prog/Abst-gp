from sqlalchemy.orm import Session
from typing import List, Dict, Any
from app.services.v6.rag.embedding_provider import EmbeddingProviderInterface, MockEmbeddingProvider
from app.services.v6.rag.vector_store import VectorStoreInterface, DeterministicVectorStore

class EvidenceRetrievalService:
    def __init__(self, embedder: EmbeddingProviderInterface = None, store: VectorStoreInterface = None):
        self.embedder = embedder or MockEmbeddingProvider()
        self.store = store or DeterministicVectorStore()
        
    def retrieve(self, db: Session, query: str, tenant_id: str, case_id: int, top_k: int = 3) -> List[Dict[str, Any]]:
        """
        Orchestrates embedding the query and searching the vector store.
        """
        query_embedding = self.embedder.embed_query(query)
        chunks = self.store.search(db, query_embedding, tenant_id, case_id, top_k=top_k)
        return chunks
