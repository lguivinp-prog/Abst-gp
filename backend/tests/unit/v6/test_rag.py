from app.services.v6.rag.chunking_service import DocumentChunkService
from app.services.v6.rag.embedding_provider import MockEmbeddingProvider
from app.services.v6.rag.vector_store import DeterministicVectorStore
from app.services.v6.rag.retrieval_service import EvidenceRetrievalService
from app.services.v6.rag.rag_context_builder import RAGContextBuilder
from app.models.v6.document_chunk import DocumentChunk
from app.models.domain import CaseFile
from sqlalchemy.orm import Session

def test_chunking_service():
    text = "Paragraph 1\n\nParagraph 2\n\nParagraph 3"
    chunks = DocumentChunkService.chunk_document(1, 1, "tenant_a", text, "Anexo")
    assert len(chunks) == 3
    assert chunks[0].text == "Paragraph 1"
    assert chunks[1].chunk_index == 1

def test_deterministic_retrieval_isolation(db_session: Session):
    # Setup Data
    case_a = CaseFile(name="Case A", type="BIENES", tenant_id="tenant_a")
    case_b = CaseFile(name="Case B", type="BIENES", tenant_id="tenant_a")
    case_c = CaseFile(name="Case C", type="BIENES", tenant_id="tenant_b")
    
    db_session.add_all([case_a, case_b, case_c])
    db_session.commit()
    
    chunk_a = DocumentChunk(document_id=1, case_id=case_a.id, tenant_id="tenant_a", chunk_index=0, text="A", hash="a", source_type="doc")
    chunk_b = DocumentChunk(document_id=2, case_id=case_b.id, tenant_id="tenant_a", chunk_index=0, text="B", hash="b", source_type="doc")
    chunk_c = DocumentChunk(document_id=3, case_id=case_c.id, tenant_id="tenant_b", chunk_index=0, text="C", hash="c", source_type="doc")
    
    db_session.add_all([chunk_a, chunk_b, chunk_c])
    db_session.commit()
    
    retriever = EvidenceRetrievalService()
    
    # 1. Retrieve for Case A, Tenant A
    res_a = retriever.retrieve(db_session, "query", "tenant_a", case_a.id)
    assert len(res_a) == 1
    assert res_a[0]["text"] == "A"
    
    # 2. Retrieve for Case B, Tenant A (Ensuring isolation within same tenant)
    res_b = retriever.retrieve(db_session, "query", "tenant_a", case_b.id)
    assert len(res_b) == 1
    assert res_b[0]["text"] == "B"
    
    # 3. Retrieve for Case C, Tenant A (Cross-tenant attempt)
    res_c = retriever.retrieve(db_session, "query", "tenant_a", case_c.id)
    assert len(res_c) == 0 # Should return nothing because case_c belongs to tenant_b, filtering fails on tenant constraint

def test_rag_context_builder():
    chunks = [
        {"document_id": 1, "page": 1, "text": "Fragment 1"},
        {"document_id": 1, "page": 2, "text": "Fragment 2"}
    ]
    context = RAGContextBuilder.build_context(chunks)
    assert "retrieved_evidence" in context
    assert len(context["retrieved_evidence"]) == 2
