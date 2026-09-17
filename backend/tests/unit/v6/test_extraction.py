import pytest
from app.services.v6.extraction.contract_extractor import extract_requirements_from_text, is_template_instruction
from app.services.v6.extraction.service import RequirementExtractionService
from app.models.v6.case_requirement_matrix import CaseRequirementMatrix
from app.models.v6.case_procurement_item import CaseProcurementItem
from app.models.domain import CaseFile, UploadedDocument


def test_contract_extractor_regexes():
    res1 = extract_requirements_from_text("GARANTIA: 12 meses")
    assert len(res1["requirements"]) == 1
    req1 = res1["requirements"][0]
    assert req1["key"] == "GARANTIA"
    assert req1["numeric_value"] == 12.0
    assert req1["unit"] == "meses"
    assert req1["comparator"] == "MIN"

    res2 = extract_requirements_from_text("Garantía mínima: 24 meses")
    req2 = res2["requirements"][0]
    assert req2["key"] == "GARANTIA"
    assert req2["numeric_value"] == 24.0

    res3 = extract_requirements_from_text("PLAZO DE ENTREGA: 30 días")
    req3 = res3["requirements"][0]
    assert req3["key"] == "PLAZO_ENTREGA"
    assert req3["numeric_value"] == 30.0
    assert req3["comparator"] == "MAX"

    res4 = extract_requirements_from_text("PLAZO MAXIMO: 30 dias")
    req4 = res4["requirements"][0]
    assert req4["key"] == "PLAZO_ENTREGA"

    res5 = extract_requirements_from_text("VIDA UTIL: 5 años")
    req5 = res5["requirements"][0]
    assert req5["key"] == "VIDA_UTIL"
    assert req5["numeric_value"] == 5.0

    res6 = extract_requirements_from_text("VIDA ÚTIL MÍNIMA: 5 años")
    req6 = res6["requirements"][0]
    assert req6["key"] == "VIDA_UTIL"

def test_template_instruction_filter():
    assert is_template_instruction("[En caso corresponda ... indicar ...]") is True
    assert is_template_instruction("[De preverse la garantía...]") is True
    assert is_template_instruction("Condiciones de la garantía: Indicar") is True
    assert is_template_instruction("Período de garantía: Por tiempo") is True
    assert is_template_instruction("Inicio del cómputo a partir de") is True
    assert is_template_instruction("5.12 Garantía comercial") is True
    
    assert is_template_instruction("Alcance de la garantía: Contra defectos de diseño y/o fabricación...") is False

class MockExtractorResult:
    def __init__(self, reqs, items):
        self.requirements = reqs
        self.items = items

class MockCandidate:
    def __init__(self, req_type, desc, value, mandatory, conf):
        self.requirement_type = req_type
        self.description = desc
        self.value = value
        self.mandatory = mandatory
        self.confidence = conf
        self.source_document = "doc"
        self.source_page = 1
        self.source_fragment = "frag"

class MockItem:
    def __init__(self, item_number, desc, qty, unit, needs_review, conf):
        self.item_number = item_number
        self.description = desc
        self.quantity = qty
        self.unit = unit
        self.needs_review = needs_review
        self.confidence = conf
        self.source_page = 1
        self.specifications = []

class MockProvider:
    def extract(self, text, source_document):
        reqs = [
            MockCandidate("TECHNICAL", "GARANTIA: 12 meses", "12", True, 0.9), # Should be deduplicated by contractual
            MockCandidate("TECHNICAL", "Especificación técnica real", "X", True, 0.9),
            MockCandidate("TECHNICAL", "Especificación técnica real", "X", True, 0.9), # Should be deduplicated by identical description
            MockCandidate("TECHNICAL", "[En caso corresponda, llenar esto]", "", False, 0.9), # Should be filtered by template filter
            MockCandidate("CONTEXT", "Contexto general", "", False, 0.9)
        ]
        items = [
            MockItem("1", "Item 1", 10, "UNIDAD", False, 0.9),
            MockItem("2", "Item 2", 5, "UNIDAD", False, 0.9)
        ]
        return MockExtractorResult(reqs, items)

def test_idempotency_and_deduplication(db_session):
    case_file = CaseFile(id=1, title="Test", contract_type="BIENES", tenant_id="mega_tenant")
    doc = UploadedDocument(id=10, case_id=1, document_type="requirement", original_filename="doc.pdf", stored_path="/tmp/doc.pdf", mime_type="application/pdf")
    db_session.add(case_file)
    db_session.add(doc)
    db_session.commit()
    
    service = RequirementExtractionService(extractor=MockProvider())
    
    # First execution
    service.process_text_and_propose(db_session, case_id=1, user_id=1, tenant_id="mega_tenant", text="GARANTIA: 12 meses", document_name="doc.pdf", document_id=10)
    
    reqs = db_session.query(CaseRequirementMatrix).all()
    # 1 contractual (Garantia), 1 technical (Especificación técnica real), 1 context (Contexto general)
    assert len(reqs) == 3
    
    req_types = [r.requirement_type for r in reqs]
    assert "CONTRACTUAL" in req_types
    assert "TECHNICAL" in req_types
    assert "CONTEXT" in req_types
    
    items = db_session.query(CaseProcurementItem).all()
    assert len(items) == 2
    
    # Now modify one requirement to simulate human intervention
    req_to_modify = db_session.query(CaseRequirementMatrix).filter_by(requirement_type="CONTEXT").first()
    req_to_modify.status = "VALIDATED"
    db_session.commit()
    
    item_to_modify = db_session.query(CaseProcurementItem).filter_by(item_number="1").first()
    item_to_modify.status = "VALIDATED"
    original_item_id = item_to_modify.id
    db_session.commit()
    
    # Second execution (Idempotent)
    service.process_text_and_propose(db_session, case_id=1, user_id=1, tenant_id="mega_tenant", text="GARANTIA: 12 meses", document_name="doc.pdf", document_id=10)
    
    # Assert requirements
    reqs_after = db_session.query(CaseRequirementMatrix).all()
    assert len(reqs_after) == 3
    
    # Check that the modified requirement kept its status
    modified_req = db_session.query(CaseRequirementMatrix).filter_by(requirement_type="CONTEXT").first()
    assert modified_req.status == "VALIDATED"
    
    # Assert items
    items_after = db_session.query(CaseProcurementItem).all()
    assert len(items_after) == 2
    
    # Check that the item kept its ID and isn't duplicated
    modified_item_after = db_session.query(CaseProcurementItem).filter_by(item_number="1").all()
    assert len(modified_item_after) == 1
    assert modified_item_after[0].id == original_item_id
    assert modified_item_after[0].status == "VALIDATED"
