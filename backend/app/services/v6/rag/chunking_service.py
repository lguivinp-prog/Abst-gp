from typing import List, Dict, Any
from app.models.v6.document_chunk import DocumentChunk
import hashlib

class DocumentChunkService:
    @staticmethod
    def chunk_document(document_id: int, case_id: int, tenant_id: str, text: str, source_type: str, page: int = 1) -> List[DocumentChunk]:
        """
        Simulates segmenting a document into smaller chunks.
        For now, simply chunks by paragraphs or fixed length strings.
        """
        raw_chunks = text.split("\n\n")
        chunks = []
        for i, raw_chunk in enumerate(raw_chunks):
            if not raw_chunk.strip():
                continue
                
            chunk_hash = hashlib.sha256(raw_chunk.encode('utf-8')).hexdigest()
            chunk = DocumentChunk(
                document_id=document_id,
                case_id=case_id,
                tenant_id=tenant_id,
                page=page,
                chunk_index=i,
                text=raw_chunk.strip(),
                hash=chunk_hash,
                source_type=source_type,
                chunk_metadata={"length": len(raw_chunk)}
            )
            chunks.append(chunk)
            
        return chunks
