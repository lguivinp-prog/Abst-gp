from typing import List
from app.models.domain import ParsedSection
from app.services.extraction_engine.models.document import StructuredDocument

class StructuredDocumentAdapter:
    """
    Adapter that strictly transforms a V2 StructuredDocument into V1 ParsedSection instances.
    This ensures that the React frontend and subsequent pipeline steps remain completely unmodified.
    """
    
    @staticmethod
    def to_parsed_sections(case_id: int, structured_doc: StructuredDocument, document_id: int) -> List[ParsedSection]:
        parsed_sections = []
        
        # 1. Map Semantic Blocks to ParsedSections
        order = 1
        for block in structured_doc.blocks:
            if block.type == "section":
                title = block.normalized_text if block.normalized_text else block.original_text
                
                # Extract Roman numerals if applicable
                roman = ""
                if block.original_text:
                    parts = block.original_text.split()
                    if parts and parts[0].endswith("."):
                        roman_cand = parts[0][:-1]
                        if all(c in "IVXLCDM" for c in roman_cand.upper()):
                            roman = roman_cand.upper()
                
                metadata = {
                    "source": "ocr_v2",
                    "confidence": block.confidence,
                    "bounding_box": block.bounding_box,
                    "page": block.page,
                    "score_v2": structured_doc.metadata.get("evaluation", {}).get("score", 0.0)
                }
                
                # Format content
                content_text = ""
                if isinstance(block.content, list):
                    content_text = "\n".join([str(c) for c in block.content])
                else:
                    content_text = str(block.content)
                
                sec = ParsedSection(
                    case_id=case_id,
                    document_id=document_id,
                    original_roman=roman if roman else None,
                    original_order=order,
                    title=title,
                    original_text=content_text,
                    cleaned_text=content_text,
                    normalized_text=title,
                    current_text=content_text,
                    structure_json=[],
                    corrections_json=[],
                    warnings_json=[],
                    extraction_metadata=metadata,
                    confidence_score=block.confidence,
                    review_status="pending_review"
                )
                parsed_sections.append(sec)
                order += 1
                
        if not parsed_sections and structured_doc.blocks:
            # Fallback if no structural sections were detected but there is content
            content_text = []
            for block in structured_doc.blocks:
                if not block.style.get("remove_from_content"):
                    if isinstance(block.content, list):
                        content_text.append("\n".join([str(c) for c in block.content]))
                    else:
                        content_text.append(str(block.content))
            
            if content_text:
                full_content = "\n\n".join(content_text)
                sec = ParsedSection(
                    case_id=case_id,
                    document_id=document_id,
                    original_roman=None,
                    original_order=1,
                    title="CONTENIDO GENERAL",
                    original_text=full_content,
                    cleaned_text=full_content,
                    normalized_text="CONTENIDO GENERAL",
                    current_text=full_content,
                    structure_json=[],
                    corrections_json=[],
                    warnings_json=[],
                    extraction_metadata={"source": "ocr_v2", "fallback": True},
                    confidence_score=0.5,
                    review_status="pending_review"
                )
                parsed_sections.append(sec)

        # Attach tables and entities to the first section's metadata
        if parsed_sections:
            if structured_doc.tables:
                parsed_sections[0].extraction_metadata["tables_detected"] = [t.model_dump() for t in structured_doc.tables]
            if structured_doc.entities:
                parsed_sections[0].extraction_metadata["entities_detected"] = [e.model_dump() for e in structured_doc.entities]
                
        return parsed_sections
