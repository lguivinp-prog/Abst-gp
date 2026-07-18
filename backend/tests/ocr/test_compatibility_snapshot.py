import os
import json

from app.services.extraction_engine.v2_pipeline import OCRV2Pipeline
from app.services.extraction_engine.adapters.structured_document_adapter import StructuredDocumentAdapter
from app.models.domain import ParsedSection

def test_v2_to_parsed_sections_contract():
    from app.services.extraction_engine.models.document import StructuredDocument, DocumentBlock
    
    doc = StructuredDocument()
    doc.blocks.append(DocumentBlock(
        type="section",
        content="I. FINALIDAD PÚBLICA\nTexto de prueba.",
        original_text="I. FINALIDAD PÚBLICA\nTexto de prueba.",
        normalized_text="FINALIDAD PÚBLICA",
        page=1,
        confidence=0.99
    ))
    
    doc.metadata = {"evaluation": {"score": 0.95}}
    
    case_id = 999
    sections = StructuredDocumentAdapter.to_parsed_sections(case_id, doc, 999)
    
    assert len(sections) == 1
    sec = sections[0]
    
    assert sec.case_id == 999
    assert sec.original_roman == "I"
    assert sec.title == "FINALIDAD PÚBLICA"
    assert "Texto de prueba" in sec.cleaned_text
    assert sec.review_status == "pending_review"
    assert sec.extraction_metadata["source"] == "ocr_v2"
    assert sec.extraction_metadata["confidence"] == 0.99
    assert sec.confidence_score == 0.99
    print("test_v2_to_parsed_sections_contract: PASSED")

def test_snapshot_adapter_with_tables():
    from app.services.extraction_engine.models.document import StructuredDocument, DocumentBlock, TableBlock
    
    doc = StructuredDocument()
    doc.blocks.append(DocumentBlock(
        type="section",
        content="Contenido con tabla",
        original_text="Contenido con tabla",
        normalized_text="Contenido con tabla",
        page=1,
        confidence=0.90
    ))
    
    tb = TableBlock(page_number=1, confidence=0.9, extraction_method="pdfplumber")
    tb.columns = ["Col1", "Col2"]
    tb.rows = [["A", "B"]]
    doc.tables.append(tb)
    
    case_id = 1000
    sections = StructuredDocumentAdapter.to_parsed_sections(case_id, doc, 999)
    
    assert len(sections) == 1
    sec = sections[0]
    
    assert "tables_detected" in sec.extraction_metadata
    assert len(sec.extraction_metadata["tables_detected"]) == 1
    assert sec.extraction_metadata["tables_detected"][0]["columns"] == ["Col1", "Col2"]
    print("test_snapshot_adapter_with_tables: PASSED")

if __name__ == "__main__":
    test_v2_to_parsed_sections_contract()
    test_snapshot_adapter_with_tables()
    print("All tests passed.")
