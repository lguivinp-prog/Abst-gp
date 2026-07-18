import pytest
from app.services.extraction_engine.adapters.structured_document_adapter import StructuredDocumentAdapter
from app.services.extraction_engine.models.document import StructuredDocument, DocumentBlock

def test_missing_document_id():
    doc = StructuredDocument(
        content="Test",
        blocks=[DocumentBlock(type="section", content="Hello", original_text="Hello", confidence=1.0, page=1)],
        metadata={"evaluation": {"score": 1.0}}
    )
    with pytest.raises(TypeError):
        # Python will raise TypeError missing 1 required positional argument: document_id
        StructuredDocumentAdapter.to_parsed_sections(1, doc)
