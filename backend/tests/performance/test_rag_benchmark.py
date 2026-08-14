import pytest
from app.services.v6.rag.evidence_retrieval_service import EvidenceRetrievalService

class MockVectorStore:
    def search(self, query, top_k, filters):
        # Return mock candidates
        return [
            {"text": "Experiencia en consultoria de servicios", "score": 0.8},
            {"text": "Venta de bienes informaticos", "score": 0.7},
            {"text": "Sin relacion directa", "score": 0.2},
            {"text": "Consultoria especializada", "score": 0.6},
            {"text": "Texto aleatorio 1", "score": 0.5},
            {"text": "Texto aleatorio 2", "score": 0.4},
            {"text": "Texto aleatorio 3", "score": 0.3},
            {"text": "Texto aleatorio 4", "score": 0.2},
            {"text": "Texto aleatorio 5", "score": 0.1},
            {"text": "Texto aleatorio 6", "score": 0.05}
        ][:top_k]

def test_dynamic_top_k():
    store = MockVectorStore()
    service = EvidenceRetrievalService(store)
    
    # Simple query (length < 5) -> K=5
    res_simple = service.retrieve_evidence("t1", 1, 1, "Experiencia servicios")
    assert res_simple["metadata"]["top_k_applied"] == 5
    assert len(res_simple["chunks"]) == 5
    
    # Complex query (length 5-14) -> K=10
    res_complex = service.retrieve_evidence("t1", 1, 1, "Demostrar experiencia en servicios de consultoria especializada informatica")
    assert res_complex["metadata"]["top_k_applied"] == 10
    assert len(res_complex["chunks"]) == 10
    
    # Very complex query -> K=15
    res_max = service.retrieve_evidence("t1", 1, 1, "a b c d e f g h i j k l m n o p q")
    assert res_max["metadata"]["top_k_applied"] == 15

def test_heuristic_reranking():
    store = MockVectorStore()
    service = EvidenceRetrievalService(store)
    
    # Query contains 'consultoria'
    res = service.retrieve_evidence("t1", 1, 1, "Experiencia servicios consultoria")
    chunks = res["chunks"]
    
    # "Consultoria especializada" (originally score 0.6) might bump up because of 'consultoria' term hit
    for chunk in chunks:
        assert "rerank_score" in chunk
        assert chunk["rerank_score"] >= chunk["retrieval_score"]

def test_long_document_generator():
    store = MockVectorStore()
    service = EvidenceRetrievalService(store)
    
    # Simulate a document of 2000 words
    long_doc = "word " * 2000
    
    gen = service.process_large_document_stream(long_doc)
    
    # Verify it yields chunks without returning a massive list all at once
    first_chunk = next(gen)
    assert first_chunk is not None
    assert len(first_chunk["text"].split()) == 1024
    
    # Next chunk should start overlapping
    second_chunk = next(gen)
    assert len(second_chunk["text"].split()) <= 1024
    assert second_chunk["strategy"] == "chunk_v1_1024_128"
