import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

from app.services.v6.extraction.requirement_classifier import classify_requirement
from app.models.v6.case_requirement_matrix import RequirementCategory, RequirementPhase

class DummyItem:
    def __init__(self, id, description):
        self.id = id
        self.description = description

class DummySpec:
    def __init__(self, item_id, name, value):
        self.procurement_item_id = item_id
        self.name = name
        self.value = value

def test_classifier_explicit_assertions():
    item_grapa = DummyItem(19, "GRAPA DE ACERO 3/4 in")
    item_alambre = DummyItem(18, "ALAMBRE DE ACERO GALVANIZADO")
    item_pintura = DummyItem(20, "PINTURA ESMALTE SINTETICO")
    item_thinner = DummyItem(21, "THINNER ACRILICO")
    
    procurement_items = [item_grapa, item_alambre, item_pintura, item_thinner]
    
    # 1. "MATERIA PRIMA: Acero galvanizado" -> item grapa (with spec evidence)
    spec_grapa = DummySpec(19, "MATERIA PRIMA", "Acero")
    
    res1 = classify_requirement(
        "MATERIA PRIMA: Acero galvanizado", 
        procurement_items, 
        [spec_grapa]
    )
    assert res1["category"] == RequirementCategory.ITEM_SPECIFICATION, f"Expected ITEM_SPECIFICATION, got {res1['category']}"
    assert res1["procurement_item_id"] == 19, f"Expected 19, got {res1['procurement_item_id']}"

    # 2. "TIPO: Grapa para fijación de alambre" -> item grapa
    res2 = classify_requirement(
        "TIPO: Grapa para fijación de alambre",
        procurement_items,
        []
    )
    assert res2["category"] == RequirementCategory.ITEM_SPECIFICATION
    assert res2["procurement_item_id"] == 19
    
    # 3. "TIPO: Esmalte acrílico..." -> pintura, NO thinner
    res3 = classify_requirement(
        "TIPO: Esmalte acrílico brillante",
        procurement_items,
        []
    )
    assert res3["category"] == RequirementCategory.ITEM_SPECIFICATION
    assert res3["procurement_item_id"] == 20
    
    # 4. "Alcance de la garantía: Contra defectos..." -> GENERAL_OBLIGATION / CONTRACT_EXECUTION / None
    res4 = classify_requirement(
        "Alcance de la garantía: Contra defectos de diseño y/o fabricación",
        procurement_items,
        []
    )
    assert res4["category"] == RequirementCategory.GENERAL_OBLIGATION
    assert res4["phase"] == RequirementPhase.CONTRACT_EXECUTION
    assert res4["procurement_item_id"] is None
    
    print("All tests passed!")

if __name__ == "__main__":
    test_classifier_explicit_assertions()
