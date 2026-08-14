from typing import List, Dict, Any

class RAGContextBuilder:
    @staticmethod
    def build_context(retrieved_chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Builds a compact context payload containing only the retrieved chunks.
        """
        context = {
            "retrieved_evidence": []
        }
        
        for c in retrieved_chunks:
            context["retrieved_evidence"].append({
                "document_id": c["document_id"],
                "page": c["page"],
                "content": c["text"]
            })
            
        return context
