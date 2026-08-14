from app.services.v6.engines.improvement_engine import DeterministicImprovementEngine
from app.models.v6.offer_evidence import OfferEvidence

def test_improvement_engine_price_rule():
    engine = DeterministicImprovementEngine()
    # Price is never an improvement
    assert engine.detect_improvement("Precio 100 soles", "Precio 50 soles") == False
    assert engine.detect_improvement("Monto maximo 5000 dolares", "4000 dolares") == False

def test_improvement_engine_time_rule():
    engine = DeterministicImprovementEngine()
    # Lower time is improvement
    assert engine.detect_improvement("Plazo 10 dias", "5 dias") == True
    assert engine.detect_improvement("Entrega 15 dias", "Entrega en 15 dias") == False
    assert engine.detect_improvement("20 dias", "30 dias") == False

def test_improvement_engine_warranty_rule():
    engine = DeterministicImprovementEngine()
    # Higher warranty is improvement
    assert engine.detect_improvement("Garantia 12 meses", "24 meses") == True
    assert engine.detect_improvement("12 meses", "6 meses") == False

def test_improvement_engine_conflict_detection():
    engine = DeterministicImprovementEngine()
    ev1 = OfferEvidence(fragment="10 dias")
    ev2 = OfferEvidence(fragment="10 dias")
    assert engine.detect_conflict([ev1, ev2]) == False
    
    ev3 = OfferEvidence(fragment="5 dias")
    assert engine.detect_conflict([ev1, ev3]) == True
